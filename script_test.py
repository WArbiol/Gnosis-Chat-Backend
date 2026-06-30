import os
import json
from unstructured.partition.pdf import partition_pdf

# Configurações
HF_TOKEN = "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"
# Lista de PDFs disponíveis para teste (Descomente o que deseja testar)
PDF_OPTIONS = [
    "pdfs/1a_camara/Manual de Magia Prática (PT).pdf",
    "pdfs/1a_camara/A Falsa Personalidade (ES).pdf",
    "pdfs/1a_camara/Apontamentos Secretos de Um Guru (ES).pdf",
    "pdfs/1a_camara/Rosa Ígnea (ES).pdf",
    "pdfs/1a_camara/A Mulher Gnóstica (PT).pdf",
    "pdfs/1a_camara/O Livro Amarelo (PT).pdf",
    "pdfs/1a_camara/Tratado de Psicologia Revolucionária (PT).pdf",
    "pdfs/1a_camara/Curso Zodiacal (PT).pdf",
    "pdfs/1a_camara/Tratado de Medicina Oculta e Magia Prática (PT).pdf",
    "pdfs/1a_camara/A Via Crucis e as Sete Palavras (ES).pdf",
    "pdfs/1a_camara/O Divino Daimon (ES).pdf",
    "pdfs/1a_camara/Recital a Um Povo (PT).pdf",
    "pdfs/1a_camara/A Ciência de Orar (ES).pdf",
    "pdfs/1a_camara/Vida e Obra de Um Homem (ES).pdf",
    "pdfs/1a_camara/Plantas e Suas Propriedades Curativas (ES).pdf",
    "pdfs/1a_camara/Meu Regresso ao Tibet (ES).pdf",
    "pdfs/1a_camara/Orientações Para a Juventude (PT).pdf",
    "pdfs/1a_camara/A Doutrina Secreta de Anahuac (ES).pdf",
    "pdfs/1a_camara/Pistis Sophia Desvelada pelo V. M. Samael Aun Weor (PT).pdf",
    "pdfs/1a_camara/Diálogos (ES).pdf",
    "pdfs/1a_camara/Magia Crística Asteca (PT).pdf",
    "pdfs/1a_camara/A Mensagem de Aquário (PT).pdf",
    "pdfs/1a_camara/As Respostas que Deu um Lama (ES).pdf",
    "pdfs/1a_camara/A História do Cupim (PT).pdf",
    "pdfs/1a_camara/Tratado de Alquimia Sexual (ES).pdf",
    "pdfs/1a_camara/A Grande Rebelião (PT).pdf",
    "pdfs/1a_camara/O Mistério do Áureo Florescer (PT).pdf",
    "pdfs/1a_camara/Tratado de Medicina Natural, Quirologia, Iridologia e Sintomatologia (PT).pdf",
    "pdfs/1a_camara/Assim Está a Humanidade (PT).pdf",
    "pdfs/1a_camara/As Três Montanhas (PT).pdf",
    "pdfs/1a_camara/Diálogos Esotéricos (ES).pdf",
    "pdfs/1a_camara/A Era de Aquário (ES).pdf",
    "pdfs/1a_camara/Introdução à Gnosis (PT).pdf",
    "pdfs/1a_camara/Estudo e Análise do Eu (PT).pdf",
    "pdfs/1a_camara/As Escolas Esotéricas (PT).pdf",
    "pdfs/1a_camara/Alquimia I (ES).pdf",
    "pdfs/1a_camara/O Cristo Social (ES).pdf",
    "pdfs/1a_camara/Curso de Gnosis (ES).pdf",
    "pdfs/1a_camara/Música, Meditação e Iluminação (PT).pdf",
    "pdfs/1a_camara/Tempos Apocalípticos (Mensagem de Natal) (ES).pdf",
    "pdfs/1a_camara/Os Corpos Solares (ES).pdf",
    "pdfs/1a_camara/Os Mistérios Maiores (PT).pdf",
    # 2a Camara
    "pdfs/2a_camara/As Joias do Dragão Amarelo - Tomo I.pdf",
    "pdfs/2a_camara/Os Sacramentos da Câmara Nupcial.pdf",
    "pdfs/2a_camara/LA LEY DEL DESTINO (Conv. diciembre 2002 - MLL).pdf",
    "pdfs/2a_camara/CIENCIA Y RELIGION - EL ULTIMATUM (Convivencia Semana Santa 2003 - ML.pdf",
    "pdfs/2a_camara/EL AMOR Y LA PAZ (Convivencia agosto 2003 - MLL).pdf",
    "pdfs/2a_camara/MENSAJE DE AÑO NUEVO 1994.pdf",
    "pdfs/2a_camara/CONFERENCIAS INEDITAS (Recopilación 27 Cátedras).pdf",
    "pdfs/2a_camara/ALMA BLANCA (Convivencia Semana Santa 2002 - MLL).pdf",
    "pdfs/2a_camara/MENSAJE DE NAVIDAD 1997.pdf",
    "pdfs/2a_camara/MEMORIAS CONGRESO GNOSTICO INTERNACIONAL DE REPUBLICA DOMINICANA 1997 - NO ESTA.pdf",
    "pdfs/2a_camara/PSICOANALISIS I (Conf. Entre Febrero Y Abril 1984 - MLL).pdf",
    "pdfs/2a_camara/ANALES Y FUNDAMENTOS CONGRESO GNOSTICO INTERNACIONAL 1995.pdf",
    "pdfs/2a_camara/DIALOGOS ESOTERICOS.pdf",
    "pdfs/2a_camara/LA MUERTE Y EL DESPERTAR (Conv. Bogotá junio 2004).pdf",
    "pdfs/2a_camara/EL ORIGEN DEL MONASTERIO LUMEN DE LUMINE 11 DE SEPTIEMBRE 2003.pdf",
    "pdfs/2a_camara/PSICOANALISIS II (Conf. entre febrero y abril 1984 - MLL).pdf",
    "pdfs/2a_camara/EL REGRESO DE MOISES (Conv. Semana Santa 2004 - MLL).pdf",
    "pdfs/2a_camara/EL HOMBRE HUMANO, DIVINO Y ESPIRITUAL (Conv. Nov 1994 - Sto Grial).pdf",
    "pdfs/2a_camara/MENSAJE DE AÑO NUEVO 1993  ( Libro En Donde Enseña Aspectos De Las Iniciaciones ).pdf",
    "pdfs/2a_camara/EL BARCO HACIA EL TRIUNFO (Conv. fevereiro 2004 - MLL).pdf",
    "pdfs/2a_camara/LA IGLESIA RESTAURADA.pdf",
    "pdfs/2a_camara/Los Misterios Ocultos del Divino Daimon.pdf",
    "pdfs/2a_camara/LOS MISTERIOS DE ELEUSIS (Conf. en abril 2000 - MLL.pdf",
    "pdfs/2a_camara/DIALOGOS.pdf",
    "pdfs/2a_camara/LA MUJER EN SU CRISTIFICACION.pdf",
    "pdfs/2a_camara/EL EVANGELIO DE MOISES (Conv. agosto 2004 - MLL).pdf",
    "pdfs/2a_camara/As Joias do Dragão Amarelo - Tomo III.pdf",
    "pdfs/2a_camara/HABLANDO CON EL MAESTRO (Recopilacion Llamados Telefonicos) Ampliado.pdf",
    "pdfs/2a_camara/PROVERBIOS DE LA PSICOLOGIA I, II Y III.pdf",
    "pdfs/2a_camara/As Joias do Dragão Amarelo - Tomo II.pdf",
]

# Selecione aqui os índices dos PDFs que deseja processar (ex: [0, 1, 2, 3])
SELECTED_INDICES = [0] 
SELECTED_PDFS = [os.path.join("/home/walter/Documents/AI projects/Mobile", PDF_OPTIONS[i]) for i in SELECTED_INDICES]

def process_pdf(file_path):
    pdf_no_ext = os.path.splitext(os.path.basename(file_path))[0]
    print(f"\n--- Processando: {pdf_no_ext} ---")
    
    os.environ["HF_TOKEN"] = HF_TOKEN
    
    elements = partition_pdf(
        filename=file_path,
        strategy="hi_res",
        languages=["spa", "por"],
        include_page_breaks=True,
        infer_table_structure=True,
    )

    # 1. Salvar resultado RAW do YOLOX (Antes do chunking)
    yolox_output = f"extraction_results_{pdf_no_ext}_yolox.json"
    raw_elements = [el.to_dict() for el in elements]
    with open(yolox_output, "w", encoding="utf-8") as f:
        json.dump(raw_elements, f, ensure_ascii=False, indent=2)
    print(f"-> RAW YOLOX salvo em: {yolox_output}")

    # Categorias consideradas ruído
    NOISE_CATEGORIES = {"Footer", "Header", "Image"}

    def chunk_elements(elements, pdf_name, max_chars=2000, overlap_chars=400):
        chunks = []
        current_chunk_text = ""
        current_page = 1
        current_chapter = "Início"
        
        pdf_basename = os.path.basename(pdf_name)

        def is_noise_text(text):
            t = text.strip()
            if t.isdigit(): return True
            
            ignored_strings = {"Instituto Gnosis Brasil", "Samael Aun Weor", "Lakhsmi", "www.gnosisbrasil.com"}
            
            if len(t) < 90:
                if any(s in t for s in ignored_strings): return True
                if len(t.split("-")) == 2 or len(t.split("–")) == 2: return True
            return False

        def save_current_chunk(page, chapter):
            nonlocal current_chunk_text
            if not current_chunk_text.strip(): return
            
            context_header = f"[Obra: {pdf_basename} | Cap: {chapter} | Pág: {page}]\n"
            full_text = context_header + current_chunk_text.strip()
            
            chunks.append({
                "text": full_text,
                "metadata": {
                    "pdf_name": pdf_basename,
                    "page": page,
                    "chapter": chapter,
                    "char_count": len(full_text)
                }
            })

        for element in elements:
            page = getattr(element.metadata, "page_number", None) or current_page
            if element.category == "PageBreak":
                current_page = page
                continue
            if element.category in NOISE_CATEGORIES: continue
            if is_noise_text(element.text): continue

            if element.category == "Title" and not element.text.strip().endswith("."):
                save_current_chunk(page, current_chapter)
                current_chunk_text = ""
                current_chapter = element.text.strip()
                current_page = page
                
            element_text = element.text + "\n"
            if len(current_chunk_text) + len(element_text) > max_chars:
                save_current_chunk(page, current_chapter)
                overlap_text = current_chunk_text[-overlap_chars:] if len(current_chunk_text) > overlap_chars else current_chunk_text
                current_chunk_text = overlap_text + element_text
                current_page = page 
            else:
                current_chunk_text += element_text
                current_page = page

        save_current_chunk(current_page, current_chapter)
        return chunks

    # 2. Executar o chunking e salvar
    chunked_results = chunk_elements(elements, file_path)
    chunked_output = f"extraction_results_{pdf_no_ext}.json"
    with open(chunked_output, "w", encoding="utf-8") as f:
        json.dump(chunked_results, f, ensure_ascii=False, indent=2)
    print(f"-> CHUNKS salvos em: {chunked_output}")

    return chunked_results

def main():
    for pdf_path in SELECTED_PDFS:
        if not os.path.exists(pdf_path):
            print(f"Erro: Arquivo não encontrado: {pdf_path}")
            continue
            
        try:
            process_pdf(pdf_path)
        except Exception as e:
            print(f"Erro ao processar {pdf_path}: {e}")
            import traceback
            traceback.print_exc()
    
    print("\nProcessamento da lista concluído!")

if __name__ == "__main__":
    main()
