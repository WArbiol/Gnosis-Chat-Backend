import os
import json
import time
import gc
import tempfile
import torch
import logging
import re
from pathlib import Path
from tqdm import tqdm
from unstructured.partition.pdf import partition_pdf
from pypdf import PdfReader, PdfWriter

# Força o PyTorch e o Tesseract OCR a usarem apenas 1 thread.
os.environ["OMP_NUM_THREADS"] = "2"
os.environ["OPENBLAS_NUM_THREADS"] = "2"
os.environ["MKL_NUM_THREADS"] = "2"
os.environ["VECLIB_MAXIMUM_THREADS"] = "2"
os.environ["NUMEXPR_NUM_THREADS"] = "2"

# Configurações de caminhos
BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
PDFS_DIR = DATA_DIR / "pdfs"  # Novo diretório para os PDFs de entrada
RAW_DIR = DATA_DIR / "raw"
CHUNKS_DIR = DATA_DIR / "chunks"

# Garantir que os diretórios existam
PDFS_DIR.mkdir(parents=True, exist_ok=True)
RAW_DIR.mkdir(parents=True, exist_ok=True)
CHUNKS_DIR.mkdir(parents=True, exist_ok=True)

# Categorias consideradas ruído
NOISE_CATEGORIES = {"Footer", "Header", "Image", "Table"}

# Configuração de Logging
log_file = DATA_DIR / "processing.log"
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(log_file, encoding='utf-8'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

def clean_text(text: str) -> str:
    """Remove quebras de linha e espaços duplos/excessivos."""
    return re.sub(r'\s+', ' ', text).strip()

def process_pdf(file_path: Path, max_chars=2000, overlap_chars=400):
    pdf_no_ext = file_path.stem
    chunks_output = CHUNKS_DIR / f"{pdf_no_ext}_chunks.json"
    raw_output = RAW_DIR / f"{pdf_no_ext}_yolox.json"
    
    # 0. SISTEMA DE RETOMADA (RESUME)
    if chunks_output.exists():
        logger.info(f"[{pdf_no_ext}] Já processado. Pulando...")
        return

    logger.info(f"--- Iniciando: {pdf_no_ext} ---")
    
    # 1. EXTRAÇÃO RAW
    reader = PdfReader(file_path)
    total_pages = len(reader.pages)
    PAGES_PER_BATCH = 20
    
    all_elements = []

    logger.info(f"PDF contém {total_pages} páginas. Dividindo em lotes de {PAGES_PER_BATCH}...")

    # Usando tqdm para barra de progresso nos lotes (leave=False para limpar da tela ao fim do PDF)
    for i in tqdm(range(0, total_pages, PAGES_PER_BATCH), desc=f"Lotes ({pdf_no_ext[:15]}...)", leave=False):
        writer = PdfWriter()
        start_page = i
        end_page = min(i + PAGES_PER_BATCH, total_pages)
        
        for j in range(start_page, end_page):
            writer.add_page(reader.pages[j])
            
        fd, temp_pdf_path = tempfile.mkstemp(suffix=".pdf")
        os.close(fd)
        
        with open(temp_pdf_path, "wb") as f:
            writer.write(f)

        batch_elements = partition_pdf(
            filename=temp_pdf_path,
            strategy="hi_res", 
            languages=["spa", "por"],
            include_page_breaks=True,
            infer_table_structure=False,
        )
        
        for el in batch_elements:
            if hasattr(el, 'metadata') and hasattr(el.metadata, 'page_number'):
                if el.metadata.page_number is not None:
                    el.metadata.page_number += start_page
        
        all_elements.extend(batch_elements)
        os.remove(temp_pdf_path)
        del batch_elements
        if torch.cuda.is_available():
            torch.cuda.empty_cache()
        gc.collect()

    # Salvar RAW YOLOX
    with open(raw_output, "w", encoding="utf-8") as f:
        json.dump([el.to_dict() for el in all_elements], f, ensure_ascii=False, indent=2)
    logger.info(f"RAW YOLOX salvo.")

    # 2. CHUNKING
    chunks = []
    current_chunk_text = ""
    current_page = 1
    current_chapter = "Início"
    
    # Metadados baseados no nome do arquivo e path
    if " - " in pdf_no_ext:
        parts = pdf_no_ext.rsplit(" - ", 1)
        book_name_meta = parts[0].strip()
        author_meta = parts[1].strip()
    else:
        book_name_meta = pdf_no_ext.strip()
        author_meta = "Desconhecido"
    
    # Identificar câmara pelo path ou nome
    chamber_meta = 2 if "2a_camara" in str(file_path).lower() or "/2a/" in str(file_path).lower() else 1

    def is_noise_text(text, category):
        t = text.strip()
        if t.isdigit() or t.count('.') >= 7: return True
        ignored_strings = {"Instituto Gnosis Brasil", "Samael Aun Weor", "Lakhsmi", "www.gnosisbrasil.com"}
        if t.startswith('SAMAEL AUN WEOR – EL QUINTO EVANGELIO'): return True
        if len(t) < 90:
            if any(s in t for s in ignored_strings): return True
            if (len(t.split("-")) == 2 or len(t.split("–")) == 2) and category != 'ListItem': return True
        return False

    def save_current_chunk(page, chapter):
        nonlocal current_chunk_text
        chunk_text_stripped = current_chunk_text.strip()
        if not chunk_text_stripped or len(chunk_text_stripped) < 50: return
        
        context_header = f"[Obra: {book_name_meta} | Autor: {author_meta} | Câmara: {chamber_meta} | Cap: {chapter} | Pág: {page}]\n"
        full_text = context_header + chunk_text_stripped
        
        chunks.append({
            "text": full_text,
            "metadata": {
                "pdf_name": file_path.name,
                "book_name": book_name_meta,
                "author": author_meta,
                "chamber": chamber_meta,
                "page": page,
                "chapter": chapter,
                "char_count": len(full_text)
            }
        })

    for element in all_elements:
        page = getattr(element.metadata, "page_number", None) or current_page
        if element.category == "PageBreak":
            current_page = page
            continue
        if element.category in NOISE_CATEGORIES: continue
        if is_noise_text(element.text, element.category): continue

        if element.category == "Title" and not element.text.strip().endswith((".", "!", '"')): 
            save_current_chunk(page, current_chapter)
            current_chunk_text = ""
            current_chapter = clean_text(element.text)
            current_page = page
            
        element_text = clean_text(element.text) + " "
        if len(current_chunk_text) + len(element_text) > max_chars:
            save_current_chunk(page, current_chapter)
            overlap_text = current_chunk_text[-overlap_chars:] if len(current_chunk_text) > overlap_chars else current_chunk_text
            current_chunk_text = overlap_text + element_text
            current_page = page 
        else:
            current_chunk_text += element_text
            current_page = page

    save_current_chunk(current_page, current_chapter)
    
    with open(chunks_output, "w", encoding="utf-8") as f:
        json.dump(chunks, f, ensure_ascii=False, indent=2)
    logger.info(f"CHUNKS salvos. ({len(chunks)} chunks gerados)")

    # Limpeza final
    del all_elements
    gc.collect()
    if torch.cuda.is_available():
        torch.cuda.empty_cache()

def main():
    # 1. Busca todos os PDFs na pasta data/pdfs de forma recursiva
    pdfs_to_process = list(PDFS_DIR.rglob("*.pdf"))
    
    if not pdfs_to_process:
            # Fallback para a pasta original do Walter
            ORIGINAL_PDF_DIR = Path("/home/walter/Documents/AI projects/Mobile/pdfs")
            if ORIGINAL_PDF_DIR.exists():
                pdfs_to_process = list(ORIGINAL_PDF_DIR.rglob("*.pdf"))[:1] # Pega o primeiro que achar
                if pdfs_to_process:
                    logger.warning(f"Nenhum PDF em {PDFS_DIR}. Usando fallback original: {pdfs_to_process[0]}")

    if pdfs_to_process:
        logger.info(f"Iniciando processamento de {len(pdfs_to_process)} PDFs...")
        for pdf in tqdm(pdfs_to_process, desc="Progresso Geral PDFs", position=0):
            try:
                process_pdf(pdf)
            except Exception as e:
                logger.error(f"Erro ao processar {pdf.name}: {e}")
        logger.info("Processamento total concluído!")
    else:
        logger.warning(f"Nenhum PDF encontrado em {PDFS_DIR} ou no fallback.")

if __name__ == "__main__":
    main()
