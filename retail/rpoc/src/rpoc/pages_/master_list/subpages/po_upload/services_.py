import re
import json
import base64
import time
import docx2txt

import pandas as pd
import polars as pl
import streamlit as st

from concurrent.futures import ThreadPoolExecutor
from io import BytesIO
from typing import Any

from pypdf import PdfReader , PdfWriter


PDF_CHUNK_MAX_PAGES : int = 5
PDF_LARGE_DOC_PAGE_THRESHOLD : int = 40
PDF_CHUNK_MAX_PAGES_LARGE_DOC : int = 3


def _chunk_size_for_page_count(
    page_count : int
) -> int :

    # Very large invoices (esp. multi-month consolidated statements like TGS's
    # 105-page file) pack noticeably more line items into each page than
    # smaller ones do - the same page-count-based chunk size ends up asking
    # the model to enumerate far more products per call, which measurably
    # hurt run-to-run name consistency in testing. Shrinking the chunk further
    # for these keeps per-call product density comparable to smaller docs.
    if page_count > PDF_LARGE_DOC_PAGE_THRESHOLD :
        return PDF_CHUNK_MAX_PAGES_LARGE_DOC

    return PDF_CHUNK_MAX_PAGES


def _build_known_products_block(
    master_df : Any ,
    supplier : str
) -> str :

    if (
        master_df is None or
        master_df.is_empty() or
        'Supplier' not in master_df.columns
    ) :
        return ''

    supplier_rows : Any = master_df.filter(
        pl.col('Supplier').cast(pl.String).str.strip_chars().str.to_lowercase()
        == supplier.strip().lower()
    )

    if supplier_rows.is_empty() :
        return ''

    reference_cols : list[str] = [
        c for c in ['Product Name' , 'Packing Size']
        if c in supplier_rows.columns
    ]

    supplier_rows = supplier_rows.select(reference_cols).unique()

    # * Send the FULL catalogue for this supplier so every invoice line can be
    # * reconciled to its existing master name (a random sample left most names
    # * unanchored and re-uploads came through as new products).
    product_lines : list[str] = []

    for record in supplier_rows.iter_rows(named = True) :

        product_name : str = str(record.get('Product Name' , '')).strip()

        if not product_name or product_name.lower() == 'nan' :
            continue

        raw_packing : Any = record.get('Packing Size' , '')

        try :
            packing_size : Any = int(float(raw_packing))
        except (TypeError , ValueError) :
            packing_size = raw_packing

        product_lines.append(
            f'- {product_name} | Packing Size : {packing_size}'
        )

    if not product_lines :
        return ''

    return (
        f'### ⚠️ READ THIS FIRST — EXISTING PRODUCTS FOR "{supplier}"\n'
        f'Below is the COMPLETE list of this supplier\'s products already recorded in '
        f'our system, one per line as "<Product Name> | Packing Size : <root packing '
        f'size>". The document may name the same product differently (abbreviations, '
        f'missing sizes, brand prefixes, punctuation) — e.g. "MAMEE MONSTER F/P HOT & '
        f'SPICY" may be recorded as "MAMEE MONSTER H&S 25Gx10". The document may also '
        f'contain products that are not in this list — extract those too.\n'
        f'1. NAMING : For EVERY document item, check this list first. When an item is '
        f'the same product as one listed here (same brand, variant/flavour and size), '
        f'output that Product Name EXACTLY as written (character for character) so it '
        f'reconciles with the existing record. Only when no listed product matches, '
        f'extract it as a new product named in the SAME naming pattern/style shown here. '
        f'Do not force a match between products of different variants or sizes.\n'
        f'2. PACKING SIZE CONVENTION : The same written notation can mean different '
        f'root packing sizes for different suppliers (e.g. "2x4" may be a root '
        f'packing size of 2 for one supplier but 8 for another). Infer how THIS '
        f'supplier\'s notation maps to the recorded root Packing Size from the '
        f'examples, then apply that SAME interpretation to EVERY document line item — '
        f'both the ones listed here and the new ones that are not.\n'
        f'3. Each product may appear in the output AT MOST ONCE.\n\n'
        f'EXISTING PRODUCTS :\n'
        + '\n'.join(product_lines)
        + '\n\n--- END OF EXISTING PRODUCTS. Reuse these exact names for matching '
        + 'items ; still extract every product in the document, including ones not '
        + 'listed above. ---\n'
    )


def _extract_content_from_file(
    uploaded_file : Any , 
    prompt : str
) -> list[Any] : 

    file_name : str = uploaded_file.name.lower()

    valid_extensions : tuple[str , ...] = (
        '.doc' , 
        '.docx' , 
        '.xls' , 
        '.xlsx' , 
        '.png' , 
        '.jpeg' , 
        '.jpg' , 
        '.txt' , 
        '.pdf'
    )

    if not file_name.endswith(valid_extensions) : 
        raise ValueError(f'Unsupported file extension : {file_name}')

    file_bytes : bytes = uploaded_file.getvalue()
    mime_type : str = uploaded_file.type
    content : list[Any] = []

    if 'spreadsheetml.sheet' in mime_type or 'ms-excel' in mime_type : 

        all_sheets : dict[str , Any] = pd.read_excel(
            BytesIO(file_bytes) , 
            sheet_name = None
        )

        excel_text : str = ''

        for sheet_name , df in all_sheets.items() : 

            clean_df : pd.DataFrame = df.dropna(
                how = 'all'
            ).dropna(
                axis = 1 , 
                how = 'all'
            )

            excel_text += f'--- Sheet : {sheet_name} ---\n'

            excel_text += clean_df.to_csv(
                index = False , 
                sep = '\t'
            ) + '\n\n'

        tabular_prompt : str = f'{prompt}\n\nCRITICAL: The data below is TAB-SEPARATED. Pay strict attention to the column headers. Do NOT confuse the Total Cost column with the Unit Price column.\n\nData:\n{excel_text}'

        content = [tabular_prompt]

    elif 'wordprocessingml.document' in mime_type or 'msword' in mime_type : 
        
        try : 
            text : str = docx2txt.process(BytesIO(file_bytes))
        except Exception : 
            text = file_bytes.decode(
                'utf-8' , 
                errors = 'ignore'
            )

        content = [f'{prompt}\n\nDocument Text:\n{text}']

    elif mime_type in [
        'application/pdf' , 
        'image/jpeg' , 
        'image/png'
    ] : 
        
        content = [
            prompt , 
            {
                'mime_type' : mime_type , 
                'data' : file_bytes
            }
        ]

    elif 'text/plain' in mime_type : 
        
        content = [f'{prompt}\n\n{file_bytes.decode("utf-8")}']

    else : 

        raise ValueError(f'Unsupported file type : {mime_type}')

    return content


def _extract_json_object(raw_text : str) -> str :

    # * Strip any markdown fences, then slice from the first '{' to the last '}'
    # * so stray prose before / after the JSON object can never break parsing.
    cleaned : str = re.sub(
        r'```json|```' ,
        '' ,
        raw_text ,
        flags = re.IGNORECASE
    ).strip()

    start : int = cleaned.find('{')
    end : int = cleaned.rfind('}')

    if start != -1 and end != -1 and end > start :
        return cleaned[start : end + 1]

    return cleaned


def _lenient_json_loads(raw_text : str) -> dict[str , Any] :

    # * Fast path : a clean, well-formed response.
    try :
        return json.loads(_extract_json_object(raw_text))
    except Exception :
        pass

    # * Repair a truncated / malformed object. Walk the text tracking string state
    # * and the brace/bracket stack, remembering the last position where a complete
    # * ARRAY ELEMENT closed (i.e. just after a '}' / ']' whose parent is an array).
    # * Cut there and append the matching closers so every complete product that
    # * was fully emitted survives, and the partial trailing one is dropped.
    cleaned : str = re.sub(
        r'```json|```' ,
        '' ,
        raw_text ,
        flags = re.IGNORECASE
    ).strip()

    start : int = cleaned.find('{')

    if start == -1 :
        return {}

    stack : list[str] = []
    in_string : bool = False
    escape : bool = False

    last_safe_index : int = -1
    last_safe_stack : list[str] = []

    for i in range(start , len(cleaned)) :

        ch : str = cleaned[i]

        if in_string :

            if escape :
                escape = False
            elif ch == '\\' :
                escape = True
            elif ch == '"' :
                in_string = False

            continue

        if ch == '"' :
            in_string = True

        elif ch in '{[' :
            stack.append(ch)

        elif ch in '}]' :

            if stack :
                stack.pop()

            # * A complete element sitting directly inside an array just closed.
            if stack and stack[-1] == '[' :
                last_safe_index = i + 1
                last_safe_stack = stack.copy()

    if last_safe_index == -1 :
        return {}

    repaired : str = cleaned[start : last_safe_index]

    for opener in reversed(last_safe_stack) :
        repaired += '}' if opener == '{' else ']'

    try :
        return json.loads(repaired)
    except Exception :
        return {}


def _call_llm_with_retries(
    content : list[Any] ,
    model_client : Any ,
    max_retries : int = 3
) -> dict[str , Any] :

    data : dict[str , Any] = {}
    raw_response_text : str = ''

    formatted_parts : list[dict[str , Any]] = []

    for item in content :

        if isinstance(
            item ,
            str
        ) :

            formatted_parts.append(
                {
                    'type' : 'text' ,
                    'text' : item
                }
            )

        elif isinstance(
            item ,
            dict
        ) :

            mime_type : str = item.get('mime_type' , '')
            encoded : str = base64.b64encode(item.get('data' , b'')).decode('utf-8')
            data_url : str = f'data:{mime_type};base64,{encoded}'

            if mime_type == 'application/pdf' :

                formatted_parts.append(
                    {
                        'type' : 'file' ,
                        'file' : {
                            'filename' : 'document.pdf' ,
                            'file_data' : data_url
                        }
                    }
                )

            else :

                formatted_parts.append(
                    {
                        'type' : 'image_url' ,
                        'image_url' : {'url' : data_url}
                    }
                )

    formatted_messages : list[dict[str , Any]] = [
        {
            'role' : 'user' ,
            'content' : formatted_parts
        }
    ]

    for attempt in range(max_retries) : 

        try : 

            # * Same model as before (gemini-2.5-flash), now routed via OpenRouter.
            # * JSON response format keeps output parseable ; reasoning is disabled
            # * so thinking tokens don't starve the output budget on long invoices.
            response : Any = model_client.chat.completions.create(
                model = 'google/gemini-2.5-flash' ,
                messages = formatted_messages ,
                response_format = {'type' : 'json_object'} ,
                max_tokens = 10000 ,
                extra_body = {'reasoning' : {'enabled' : False}}
            )

            raw_response_text = response.choices[0].message.content or ''

            data = _lenient_json_loads(raw_response_text)

            if not data :
                raise ValueError('No parseable JSON object found in response.')

            return data

        except Exception as e :

            st.warning(f'JSON parsing failed on attempt {attempt + 1}/{max_retries} : {e}')

            with st.expander('View Raw LLM Output (Dev Mode)') :

                st.code(
                    raw_response_text ,
                    language = 'json'
                )

            if attempt == max_retries - 1 :

                st.error('Max retries reached. Failed to parse valid JSON from LLM.')

            else :

                # Chunked PDF extraction fires several of these concurrently
                # (see PDF_CHUNK_MAX_PAGES / ThreadPoolExecutor below), which can
                # trip transient rate limits - back off before retrying instead
                # of immediately re-hitting the same limit.
                time.sleep(2 ** attempt)

    return {}


def _process_and_deduplicate_products(
    data : dict[str , Any] ,
    supplier : str | None = None
) -> list[dict[str , Any]] :

    processed_items : list[dict[str , Any]] = []

    # * A user-chosen supplier is deterministic and overrides whatever the LLM
    # * returned ; for new invoices fall back to the LLM-inferred supplier.
    raw_supplier : str = supplier or str(data.get('supplier') or 'Unknown')

    exchange_rate : float = float(
        data.get('exchange_rate' , 1.0) or 1.0
    )
    
    raw_products : list[dict[str , Any]] = data.get(
        'products' , 
        []
    )

    # Collapses multiple spaces/newlines, but keeps asterisks and original text
    supplier_display : str = re.sub(
        r'\s+' , 
        ' ' , 
        raw_supplier
    ).strip()
    
    supplier_search_key : str = supplier_display.lower()

    deduplicated_products : dict[str , dict[str , Any]] = {}

    for prod in raw_products : 

        raw_product_name : str | None = prod.get('Product Name')
        raw_product_description : str | None = prod.get('Product Description')

        original_name : str = raw_product_name or raw_product_description or 'Unknown'

        # Only standardizes white-spaces while safely safeguarding special characters
        sanitized_name_display : str = re.sub(
            r'\s+' , 
            ' ' , 
            original_name
        ).strip()
        
        sanitized_search_key : str = sanitized_name_display.lower()

        prod['Product Name'] = sanitized_name_display

        raw_pack_price : float = float(prod.get('Pack Price' , 0.0) or 0.0)

        prod['Pack Price'] = raw_pack_price

        if sanitized_search_key in deduplicated_products : 

            existing_price : float = float(
                deduplicated_products[sanitized_search_key].get('Pack Price' , 0.0) or 0.0
            )

            if existing_price == 0.0 and raw_pack_price > 0.0 : 
                deduplicated_products[sanitized_search_key]['Pack Price'] = raw_pack_price

            existing_barcode : str = deduplicated_products[sanitized_search_key].get(
                'Barcode' , 
                ''
            )

            new_barcode : str = prod.get(
                'Barcode' , 
                ''
            )

            if not existing_barcode and new_barcode : 
                deduplicated_products[sanitized_search_key]['Barcode'] = new_barcode

        else : 
            deduplicated_products[sanitized_search_key] = prod

    for product in deduplicated_products.values() : 

        try : 

            pack_price_val : float = float(product.pop('Pack Price' , 0.0) or 0.0)

            if exchange_rate > 0.0 and exchange_rate != 1.0 : 
                pack_price_val = pack_price_val / exchange_rate

            selling_price_val : float = float(product.pop('Selling Price' , 0.0) or 0.0)
            promotion_price_val : float = float(product.pop('Promotion Price' , 0.0) or 0.0)

            product_dict : dict[str , Any] = {
                'Barcode' : product.pop('Barcode' , '') , 
                'Product Name' : product.pop('Product Name' , 'Unknown') , 
                'Packing Size' : int(product.pop('Packing Size' , 1) or 1) , 
                'Pack Price' : pack_price_val , 
                'Selling Price' : selling_price_val , 
                'Promotion Price' : promotion_price_val , 
                'Supplier' : supplier_display , 
                'Redundant' : json.dumps(
                    product.get('Redundant' , [])
                )
            }

            processed_items.append(product_dict)

        except Exception as inner_e : 
            st.error(f'Error processing product dictionary : {inner_e}')

    st.write(f'Products added with exchange rate : {exchange_rate}')
    
    return processed_items


def _split_pdf_into_page_chunks(
    file_bytes : bytes ,
    max_pages_per_chunk : int
) -> list[bytes] :

    reader : PdfReader = PdfReader(BytesIO(file_bytes))
    total_pages : int = len(reader.pages)

    chunks : list[bytes] = []

    for start in range(0 , total_pages , max_pages_per_chunk) :

        writer : PdfWriter = PdfWriter()

        for page_index in range(start , min(start + max_pages_per_chunk , total_pages)) :
            writer.add_page(reader.pages[page_index])

        buffer : BytesIO = BytesIO()
        writer.write(buffer)

        chunks.append(buffer.getvalue())

    return chunks


def _call_llm_for_pdf_chunk(
    chunk_bytes : bytes ,
    mime_type : str ,
    prompt : str ,
    model_client : Any
) -> dict[str , Any] :

    content : list[Any] = [
        prompt ,
        {
            'mime_type' : mime_type ,
            'data' : chunk_bytes
        }
    ]

    parsed : dict[str , Any] = _call_llm_with_retries(
        content ,
        model_client
    )

    # A chunk can come back with valid-but-empty JSON (no exception raised, the
    # model just found nothing) - this is distinct from a JSON parse failure,
    # which _call_llm_with_retries already retries on its own. One extra retry
    # here catches that case before we accept "0 products" for a chunk that
    # visibly has page content.
    if parsed and not parsed.get('products') :

        parsed = _call_llm_with_retries(
            content ,
            model_client
        )

    return parsed


def _extract_pdf_in_chunks(
    file_bytes : bytes ,
    mime_type : str ,
    prompt : str ,
    model_client : Any ,
    max_pages_per_chunk : int = PDF_CHUNK_MAX_PAGES
) -> dict[str , Any] :

    chunks : list[bytes] = _split_pdf_into_page_chunks(
        file_bytes ,
        max_pages_per_chunk
    )

    all_products : list[dict[str , Any]] = []
    supplier : str | None = None
    exchange_rate : float | None = None

    with ThreadPoolExecutor(max_workers = 4) as executor :

        for parsed in executor.map(
            lambda chunk : _call_llm_for_pdf_chunk(
                chunk ,
                mime_type ,
                prompt ,
                model_client
            ) ,
            chunks
        ) :

            if not parsed :
                continue

            if not supplier and parsed.get('supplier') :
                supplier = parsed['supplier']

            if not exchange_rate and parsed.get('exchange_rate') :
                exchange_rate = parsed['exchange_rate']

            all_products.extend(
                parsed.get('products' , [])
            )

    return {
        'supplier' : supplier or 'Unknown' ,
        'exchange_rate' : exchange_rate or 1.0 ,
        'products' : all_products
    }


def process_document_with_llm(
    uploaded_file : Any ,
    prompt : str ,
    model_client : Any ,
    supplier : str | None = None ,
    master_df : Any = None
) -> list[dict[str , Any]] :

    try :

        augmented_prompt : str = prompt

        # * When the supplier is known (Update Existing Invoice) , pin it and send the
        # * known-products reference ; otherwise let the LLM infer the supplier.
        if supplier :

            supplier_directive : str = (
                f'\n\n### DETERMINISTIC SUPPLIER (MANDATORY)\n'
                f'The supplier for this document is already known and fixed : "{supplier}".\n'
                f'Do NOT infer, search for, or output the supplier. You may omit the '
                f'"supplier" field entirely — it will be ignored and overwritten.\n'
                f'Use this supplier to apply the Section 4 supplier-specific price rules '
                f'(Table 4.1) BEFORE any Pack Price math — if its Price Basis is '
                f'CTN_AS_PRINTED, the printed price IS the Pack Price ; never multiply it '
                f'by Packing Size.\n'
            )

            known_products_block : str = _build_known_products_block(
                master_df ,
                supplier
            )

            # * Front-load the authoritative reference + supplier directive BEFORE the
            # * large base prompt, otherwise the base prompt's "extract the longest name
            # * from the document" rules dominate and the reference list is ignored.
            augmented_prompt = known_products_block + supplier_directive + prompt

        file_name : str = uploaded_file.name.lower()

        if file_name.endswith('.pdf') :

            file_bytes : bytes = uploaded_file.getvalue()
            page_count : int = len(PdfReader(BytesIO(file_bytes)).pages)

            if page_count > PDF_CHUNK_MAX_PAGES :

                chunked_data : dict[str , Any] = _extract_pdf_in_chunks(
                    file_bytes ,
                    uploaded_file.type ,
                    augmented_prompt ,
                    model_client ,
                    _chunk_size_for_page_count(page_count)
                )

                if not chunked_data.get('products') :
                    return []

                return _process_and_deduplicate_products(
                    chunked_data ,
                    supplier
                )

        content : list[Any] = _extract_content_from_file(
            uploaded_file ,
            augmented_prompt
        )

        parsed_data : dict[str , Any] = _call_llm_with_retries(
            content ,
            model_client
        )

        if not parsed_data :
            return []

        processed_items : list[dict[str , Any]] = _process_and_deduplicate_products(
            parsed_data ,
            supplier
        )

        return processed_items

    except Exception as e :

        st.error(f'Document processing pipeline failed : {e}')

        return []