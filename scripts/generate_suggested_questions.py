import asyncio
import argparse
import glob
import json
import os
import fitz
from datetime import datetime
from pydantic import BaseModel, Field
from google import genai
from google.genai import types
from qdrant_client.models import Filter, FieldCondition, MatchValue

import sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.core.config import settings
from app.infrastructure.qdrant.qdrant_vector_store import QdrantVectorStore


class QuestionBatch(BaseModel):
    questions: list[str] = Field(
        description="Lista de perguntas curtas (entre 35 e 80 caracteres), instigantes e profundas baseadas estritamente nos ensinamentos dos trechos."
    )


def compute_hamilton_allocation(c1_books: list[dict], target_total: int = 1000) -> dict[str, int]:
    """Calcula a alocação exata de perguntas proporcional ao número de páginas (Método de Hamilton)."""
    eqe = next((b for b in c1_books if 'QUINTO EVANGELIO' in b['pdf_name'].upper()), None)
    other_books = [b for b in c1_books if b != eqe]

    eqe_quota = 70 if eqe else 0
    remaining_target = target_total - eqe_quota

    min_floor = 2
    pool = remaining_target - (len(other_books) * min_floor)
    total_other_pages = sum(b['pages'] for b in other_books)

    exact_alloc = {}
    remainders = []

    for b in other_books:
        extra = (b['pages'] / total_other_pages) * pool
        int_extra = int(extra)
        rem = extra - int_extra
        exact_alloc[b['book_name']] = min_floor + int_extra
        remainders.append((b['book_name'], rem))

    allocated_so_far = sum(exact_alloc.values())
    shortage = remaining_target - allocated_so_far

    remainders.sort(key=lambda x: x[1], reverse=True)
    for i in range(shortage):
        exact_alloc[remainders[i][0]] += 1

    if eqe:
        exact_alloc[eqe['book_name']] = eqe_quota

    return exact_alloc


async def fetch_book_chapters_and_chunks(store: QdrantVectorStore, book_name: str) -> dict[str, list[str]]:
    """Recupera os capítulos e até 2 trechos (início e clímax/conclusão) para cada capítulo do livro."""
    records, _ = store.client.scroll(
        collection_name=store.books_collection,
        scroll_filter=Filter(must=[FieldCondition(key='book_name', match=MatchValue(value=book_name))]),
        limit=250,
        with_payload=['chapter', 'page', '_node_content']
    )

    grouped: dict[str, list[str]] = {}
    for r in records:
        ch = r.payload.get('chapter')
        if not ch or ch.strip().lower() in ['prefácio', 'introdução', 'indice', 'índice']:
            continue
        nc = r.payload.get('_node_content')
        if isinstance(nc, str):
            try:
                nc = json.loads(nc)
            except Exception:
                nc = {}
        text = nc.get('text', '') if isinstance(nc, dict) else ''
        if ']' in text:
            text = text.split(']', 1)[1].strip()

        if text and len(text) > 80:
            grouped.setdefault(ch.strip(), []).append(text)

    if not grouped:
        for r in records:
            ch = r.payload.get('chapter') or "Geral"
            nc = r.payload.get('_node_content')
            if isinstance(nc, str):
                try:
                    nc = json.loads(nc)
                except Exception:
                    nc = {}
            text = nc.get('text', '') if isinstance(nc, dict) else ''
            if ']' in text:
                text = text.split(']', 1)[1].strip()
            if text and len(text) > 80:
                grouped.setdefault(ch.strip(), []).append(text)

    chapter_samples: dict[str, list[str]] = {}
    for ch, chunks in grouped.items():
        if len(chunks) == 1:
            chapter_samples[ch] = [chunks[0][:400]]
        elif len(chunks) == 2:
            chapter_samples[ch] = [chunks[0][:350], chunks[1][:350]]
        else:
            mid_idx = len(chunks) // 2
            chapter_samples[ch] = [chunks[0][:350], chunks[mid_idx][:350]]

    return chapter_samples


async def generate_questions_for_batch(
    client: genai.Client,
    semaphore: asyncio.Semaphore,
    book_name: str,
    author: str,
    batch_chapters: dict[str, list[str]],
    count: int
) -> list[str]:
    """Gera um lote focado de perguntas instigantes na perspectiva de um buscador com gemini-3.8-flash."""
    context_lines = []
    for ch, snippets in batch_chapters.items():
        context_lines.append(f"\n### {ch}")
        for i, snip in enumerate(snippets, 1):
            context_lines.append(f"Trecho {i}: \"{snip}\"")

    context_text = "\n".join(context_lines)

    prompt = (
        f"LIVRO DO ACERVO GNÓSTICO: '{book_name}'\n"
        f"AUTOR: {author}\n\n"
        f"TRECHOS DOS CAPÍTULOS:\n"
        f"{context_text}\n\n"
        f"SUA MISSÃO:\n"
        f"Gere exatamente {count} perguntas magnéticas, profundas e inspiradoras que um buscador espiritual ou estudante contemporâneo faria ao abrir o app.\n\n"
        f"DIRETRIZES FUNDAMENTAIS (ADVOGADO DO DIABO):\n"
        f"1. VOZ DO BUSCADOR (NUNCA TOM DE PROVA/VESTIBULAR):\n"
        f"   - NÃO faça perguntas como um examinador avaliando um aluno (ERRADO: 'Qual o papel de X na contenção de Y?', 'Que sacrifícios são essenciais para Z?').\n"
        f"   - FAÇA perguntas de quem busca autoconhecimento, transformação interior e respostas para a vida (CERTO: 'Por que a mente mente para si mesma?', 'Como transformar a raiva antes que ela domine a ação?').\n\n"
        f"2. VARIEDADE OBRIGATÓRIA DE INÍCIOS (MÁXIMO 1 'COMO...' NESTE LOTE):\n"
        f"   - É PROIBIDO começar a maioria das perguntas com 'Como...'. Varie obrigatoriamente os inícios entre:\n"
        f"     • 'Por que...'\n"
        f"     • 'O que acontece quando...'\n"
        f"     • 'Qual a diferença entre...'\n"
        f"     • 'É possível...'\n"
        f"     • 'De onde vem...' ou 'De onde nascem...'\n"
        f"     • 'O que a Gnosis ensina sobre...'\n"
        f"     • 'Como...' (use no máximo 1 ou 2 vezes)\n\n"
        f"3. VOCABULÁRIO ACESSÍVEL MAS PROFUNDO:\n"
        f"   - Use os termos reais da Gnosis: Ego, Essência, Consciência, Mãe Divina, Kundalini, Desdobramento Astral, Karma, Chacras, Meditação, etc.\n"
        f"   - NUNCA use palavras pomposas ou arcaicas como: 'óbice', 'exegese', 'presunção', 'outrossim', 'concomitante', 'axiomático', 'quiçá', 'porventura'.\n\n"
        f"4. TAMANHO STRICTO PARA CARD MOBILE:\n"
        f"   - Entre 35 e 80 caracteres (para caber em 2 a 3 linhas na tela do celular sem poluir o visual).\n\n"
        f"5. Retorne EXATAMENTE {count} perguntas na lista JSON."
    )

    system_instruction = (
        "Você é um curador espiritual sensível e perspicaz. "
        "Você formula perguntas que tocam no coração, no despertar da consciência e nos mistérios da alma, "
        "com linguagem clara, direta, poética e instigante, sem afetação acadêmica."
    )

    config = types.GenerateContentConfig(
        temperature=0.7,
        system_instruction=system_instruction,
        response_mime_type="application/json",
        response_schema=QuestionBatch
    )

    BANNED_WORDS = {'óbice', 'exegese', 'outrossim', 'concomitante', 'axiomático', 'ontológico', 'epistemológico', 'quiçá', 'porventura'}

    async with semaphore:
        for attempt in range(4):
            model_to_use = "gemini-3.8-flash" if attempt < 2 else "gemini-3.7-flash"
            try:
                response = await client.aio.models.generate_content(
                    model=model_to_use,
                    contents=prompt,
                    config=config
                )
                text_data = response.text or "{}"
                parsed = QuestionBatch.model_validate_json(text_data)
                clean = []
                for q in parsed.questions:
                    q = q.strip().rstrip("?") + "?"
                    # Verifica se contém palavra proibida
                    if any(bw in q.lower() for bw in BANNED_WORDS):
                        continue
                    if 30 <= len(q) <= 85:
                        clean.append(q)
                if clean:
                    return clean
            except Exception as e:
                err_str = str(e).lower()
                is_spike = any(k in err_str for k in ["503", "429", "overloaded", "spikes", "resource_exhausted"])
                if is_spike and model_to_use == "gemini-3.8-flash":
                    print(f"[{book_name}] ⚠️ Sobrecarga/Spike (503/429) no 3.8. Tentando imediatamente no gemini-3.7-flash...")
                    try:
                        fallback_resp = await client.aio.models.generate_content(
                            model="gemini-3.7-flash",
                            contents=prompt,
                            config=config
                        )
                        text_data = fallback_resp.text or "{}"
                        parsed = QuestionBatch.model_validate_json(text_data)
                        clean = []
                        for q in parsed.questions:
                            q = q.strip().rstrip("?") + "?"
                            if any(bw in q.lower() for bw in BANNED_WORDS):
                                continue
                            if 30 <= len(q) <= 85:
                                clean.append(q)
                        if clean:
                            return clean
                    except Exception as fb_err:
                        print(f"[{book_name}] Falha no fallback 3.7: {fb_err}")

                if attempt == 3:
                    print(f"[{book_name}] Falha na geração após 4 tentativas: {e}")
                await asyncio.sleep(1.5 * (attempt + 1))
    return []


async def process_single_book(
    store: QdrantVectorStore,
    client: genai.Client,
    semaphore: asyncio.Semaphore,
    book: dict,
    target_q: int,
    idx: int,
    total_books: int
) -> list[dict]:
    b_name = book['book_name']
    author = book['author']

    chapters_data = await fetch_book_chapters_and_chunks(store, b_name)
    ch_names = list(chapters_data.keys())

    if not ch_names:
        print(f"[{idx}/{total_books}] ⚠️ {b_name}: Nenhum trecho encontrado.")
        return []

    BATCH_SIZE = 10
    chapter_batches = [
        {k: chapters_data[k] for k in ch_names[i:i + BATCH_SIZE]}
        for i in range(0, len(ch_names), BATCH_SIZE)
    ]

    num_batches = len(chapter_batches)
    questions_per_batch = []
    base = target_q // num_batches
    rem = target_q % num_batches
    for i in range(num_batches):
        questions_per_batch.append(base + (1 if i < rem else 0))

    book_questions = []
    for c_batch, q_count in zip(chapter_batches, questions_per_batch):
        if q_count <= 0:
            continue
        q_list = await generate_questions_for_batch(client, semaphore, b_name, author, c_batch, q_count)
        book_questions.extend(q_list)

    print(f"[{idx:3d}/{total_books}] ✅ {b_name[:35]:<35} | Meta: {target_q:2d} -> Geradas: {len(book_questions):2d}")

    results = []
    for q in book_questions:
        results.append({
            "question": q,
            "book_name": b_name,
            "author": author,
            "chamber": 1
        })
    return results


async def run_generator(is_test: bool = False):
    print("Iniciando processo de geração de perguntas sugeridas...")
    store = QdrantVectorStore()
    client = genai.Client(api_key=settings.google_api_key)
    semaphore = asyncio.Semaphore(5)  # 5 requisições concorrentes para respeitar limites de API

    # 1. Carregar mapeamento de câmaras do Qdrant
    pdf_to_chamber = {}
    pdf_to_meta = {}
    offset = None
    while True:
        records, offset = store.client.scroll(
            collection_name=store.books_collection,
            limit=250,
            offset=offset,
            with_payload=['pdf_name', 'book_name', 'author', 'chamber']
        )
        for r in records:
            p = r.payload.get('pdf_name')
            if p and p not in pdf_to_chamber:
                pdf_to_chamber[p] = r.payload.get('chamber', 1)
                pdf_to_meta[p] = {
                    'book_name': r.payload.get('book_name'),
                    'author': r.payload.get('author') or "V.M. Samael Aun Weor"
                }
        if offset is None or len(pdf_to_chamber) >= 170:
            break

    pdf_dir = os.path.join(os.path.dirname(__file__), "..", "data", "pdfs")
    c1_books = []
    for pdf_path in glob.glob(os.path.join(pdf_dir, '**', '*.pdf'), recursive=True):
        name = os.path.basename(pdf_path)
        chamber = pdf_to_chamber.get(name, 1)
        if chamber == 1:
            doc = fitz.open(pdf_path)
            pages = len(doc)
            doc.close()
            meta = pdf_to_meta.get(name, {'book_name': name.replace('.pdf', ''), 'author': 'Desconhecido'})
            c1_books.append({
                'pdf_name': name,
                'book_name': meta['book_name'],
                'author': meta['author'],
                'pages': pages
            })

    print(f"Total de livros de 1ª Câmara identificados: {len(c1_books)}")
    allocations = compute_hamilton_allocation(c1_books, target_total=1000)
    print(f"Meta de alocação total: {sum(allocations.values())} perguntas")

    if is_test:
        test_book_names = [
            'Tratado de Psicologia Revolucionária (PT)',
            'A Linguagem dos Sonhos (ES)'
        ]
        selected_books = [b for b in c1_books if b['book_name'] in test_book_names]
        if len(selected_books) < 2:
            selected_books = [c1_books[0], c1_books[-1]]
    else:
        selected_books = c1_books

    total_selected = len(selected_books)
    print(f"\nDisparando processamento assíncrono para {total_selected} livros...")

    tasks = [
        process_single_book(
            store, client, semaphore, book, allocations.get(book['book_name'], 5), idx, total_selected
        )
        for idx, book in enumerate(selected_books, 1)
    ]

    all_book_results = await asyncio.gather(*tasks)
    flat_results = [item for sublist in all_book_results for item in sublist]

    print(f"\n=======================================================")
    print(f"🎉 GERAÇÃO CONCLUÍDA! Total de perguntas: {len(flat_results)}")
    print(f"=======================================================")

    # Salvar resultados
    output_data = {
        "chamber": 1,
        "total_questions": len(flat_results),
        "generated_at": datetime.now().isoformat(),
        "questions": [
            {
                "id": idx,
                "question": item["question"],
                "book_name": item["book_name"],
                "author": item["author"]
            }
            for idx, item in enumerate(flat_results, 1)
        ]
    }

    # Salva no backend
    backend_data_dir = os.path.join(os.path.dirname(__file__), "..", "data")
    os.makedirs(backend_data_dir, exist_ok=True)
    backend_file = os.path.join(backend_data_dir, "suggested_questions_c1.json")
    with open(backend_file, "w", encoding="utf-8") as f:
        json.dump(output_data, f, ensure_ascii=False, indent=2)
    print(f"Salvo no backend: {backend_file}")

    # Salva no frontend (assets/data)
    frontend_assets_dir = os.path.abspath(
        os.path.join(os.path.dirname(__file__), "..", "..", "gnosis-chat-front", "assets", "data")
    )
    os.makedirs(frontend_assets_dir, exist_ok=True)
    frontend_file = os.path.join(frontend_assets_dir, "suggested_questions_c1.json")
    with open(frontend_file, "w", encoding="utf-8") as f:
        json.dump(output_data, f, ensure_ascii=False, indent=2)
    print(f"Salvo no frontend: {frontend_file}")


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--test', action='store_true', default=False, help='Roda em modo teste com 2 livros')
    args = parser.parse_args()
    asyncio.run(run_generator(is_test=args.test))
