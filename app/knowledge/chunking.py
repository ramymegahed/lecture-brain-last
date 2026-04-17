from typing import List, Dict, Tuple
import re
import bisect

def clean_text(text: str) -> str:
    # Collapse horizontal whitespace, preserving newlines for semantic chunking
    text = re.sub(r'[^\S\r\n]+', ' ', text)       
    text = re.sub(r'\n{3,}', '\n\n', text) # max 2 newlines
    return text.strip()

def recursive_character_text_splitter(text: str, chunk_size: int = 1000, chunk_overlap: int = 200) -> List[Dict[str, any]]:
    """
    Simple recursive character text splitter.
    Returns a list of dicts with 'text' and 'start_idx' (offset in the original string).
    """
    chunks = []
    start = 0
    text_length = len(text)
    iteration_count = 0
    
    while start < text_length:
        iteration_count += 1
        if iteration_count % 10 == 0:
            print(f"Chunking progress: {start}/{text_length} chars ({len(chunks)} chunks so far)")

        end = start + chunk_size
        if end >= text_length:
            chunks.append({
                "text": text[start:text_length],
                "start_idx": start
            })
            break
            
        # Try to find a good breaking point
        break_point = end
        for separator in ["\n\n", "\n", ". ", " "]:
            sep_idx = text.rfind(separator, start, end)
            if sep_idx != -1:
                # CRITICAL FIX: Ensure the break point is far enough forward that subtracting
                # chunk_overlap won't push 'start' backwards, creating an infinite loop.
                if sep_idx + len(separator) > start + chunk_overlap:
                    break_point = sep_idx + len(separator)
                    break
                
        chunks.append({
            "text": text[start:break_point].strip(),
            "start_idx": start
        })
        
        # Advance the pointer
        next_start = break_point - chunk_overlap
        
        # Fallback safeguard against infinite loops 
        if next_start <= start:
            start = start + (chunk_size - chunk_overlap)
        else:
            start = next_start
            
    print(f"Chunking complete. Yielded {len(chunks)} chunks.")
    return chunks

def chunk_document(pages: List[Dict[str, any]]) -> List[Dict[str, any]]:
    """
    Takes a list of pages (dict with 'page_number' and 'text').
    Concatenates them to preserve cross-page context, chunks the full document,
    and maps the resulting chunks back to their starting page numbers.
    """
    if not pages:
        return []

    # 1. Concatenate all pages and track their character offsets
    full_text = ""
    page_offsets: List[Tuple[int, int]] = []  # List of (char_offset, page_number)
    
    for page in pages:
        current_offset = len(full_text)
        page_offsets.append((current_offset, page['page_number']))
        
        # Add page text with a separator
        page_text = page.get('text', '')
        if page_text:
            full_text += page_text + "\n\n"
            
    # 2. Split the full document
    text_chunks = recursive_character_text_splitter(full_text)
    offsets, page_numbers = zip(*page_offsets)
    
    document_chunks = []
    for chunk in text_chunks:
        if not chunk["text"]:
            continue
            
        # Find which page this chunk starts in using bisect
        # bisect_right minus 1 gives us the index of the largest offset less than or equal to start_idx
        idx = bisect.bisect_right(offsets, chunk["start_idx"]) - 1
        page_num = page_numbers[max(0, idx)]
        
        document_chunks.append({
            "text": chunk["text"],
            "page_number": page_num
        })
                
    return document_chunks

def sample_document_text(full_text: str, max_chars: int = 12000) -> str:
    """
    Instead of truncating to first N chars, take samples from
    beginning (50%), middle (25%), and end (25%) of the document.
    This gives the LLM a representative view of the full content.
    """
    n = len(full_text)
    if n <= max_chars:
        return full_text
    
    part_a = full_text[:max_chars // 2]                          # first 50%
    part_b = full_text[n//2 - max_chars//8 : n//2 + max_chars//8]  # middle 25%
    part_c = full_text[-(max_chars // 4):]                      # last 25%
    
    return f"{part_a}\n\n[...middle excerpt...]\n\n{part_b}\n\n[...end excerpt...]\n\n{part_c}"
