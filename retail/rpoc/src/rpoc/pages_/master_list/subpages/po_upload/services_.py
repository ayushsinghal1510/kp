import re
import difflib
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

    # * Send the FULL catalogue as a packing-size reference only. Names stay
    # * verbatim from the document ; asking the LLM to reuse master names made it
    # * blend names (e.g. a Lexus line renamed to a Julies product). Matching to
    # * existing products is done in code by suggest_master_matches().
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
        f'### REFERENCE — EXISTING PRODUCTS FOR "{supplier}"\n'
        f'Below is the complete list of this supplier\'s products already recorded in '
        f'our system, one per line as "<Product Name> | Packing Size : <root packing '
        f'size>". It is REFERENCE ONLY.\n'
        f'1. NAMING : Do NOT copy, borrow or blend names from this list. Every '
        f'`Product Name` MUST follow the PRODUCT NAME — VERBATIM rules below, taken '
        f'only from the document itself. Matching to existing products is done by '
        f'the system afterwards, not by you.\n'
        f'2. PACKING SIZE CONVENTION : The same written notation can mean different '
        f'root packing sizes for different suppliers (e.g. "2x4" may be a root '
        f'packing size of 2 for one supplier but 8 for another). Infer how THIS '
        f'supplier\'s notation maps to the recorded root Packing Size from the '
        f'examples, then apply that SAME interpretation to EVERY document line item — '
        f'both the ones listed here and the new ones that are not.\n'
        f'3. Each product may appear in the output AT MOST ONCE.\n\n'
        f'EXISTING PRODUCTS :\n'
        + '\n'.join(product_lines)
        + '\n\n--- END OF REFERENCE. Use it only for the packing-size convention ; '
        + 'names come verbatim from the document. Extract every product in the '
        + 'document. ---\n'
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


def _price_check_note(
    pack_price : float ,
    packing_size : float ,
    printed_unit_price : Any ,
    line_qty : Any ,
    line_amount : Any
) -> str :

    '''
    Cross-check the extracted price against the row's own printed numbers.
    Returns '' when consistent , otherwise a short warning for the review table.
    Catches misreads such as the WEIGHT column ("11.25 KG") taken as the price.
    '''

    def _f(value : Any) -> float :
        try :
            return float(str(value).replace(',' , ''))
        except (TypeError , ValueError) :
            return 0.0

    unit : float = _f(printed_unit_price)
    qty : float = _f(line_qty)
    amount : float = _f(line_amount)

    def _close(a : float , b : float) -> bool :
        return abs(a - b) <= max(0.02 , 0.01 * max(abs(a) , abs(b)))

    notes : list[str] = []

    if unit > 0 and qty > 0 and amount > 0 and not _close(unit * qty , amount) :
        notes.append(f'⚠ printed price {unit:g} × qty {qty:g} ≠ amount {amount:g}')

    if unit > 0 and pack_price > 0 and not (
        _close(pack_price , unit) or _close(pack_price , unit * packing_size)
    ) :
        notes.append(f'⚠ pack price {pack_price:g} ≠ printed price {unit:g}')

    if unit == 0 and qty > 0 and amount > 0 and pack_price > 0 and not (
        _close(pack_price * qty , amount) or _close(pack_price * qty / max(packing_size , 1) , amount)
    ) :
        notes.append(f'⚠ pack price {pack_price:g} × qty {qty:g} ≠ amount {amount:g}')

    return ' ; '.join(notes)


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

    line_amounts_sum : float = 0.0

    for product in deduplicated_products.values() :

        try :

            pack_price_val : float = float(product.pop('Pack Price' , 0.0) or 0.0)

            # * Recompute from the extracted price (not the printed amount) so a
            # * misread price shows up as a gap against the printed subtotal. Use the
            # * printed unit price (qty x printed price = line amount on any invoice) ;
            # * fall back to Pack Price when the unit price was not transcribed.
            try :
                line_price : float = float(str(product.get('Printed Unit Price') or 0).replace(',' , '')) or pack_price_val
                line_amounts_sum += float(str(product.get('Line Qty') or 0).replace(',' , '')) * line_price
            except (TypeError , ValueError) :
                pass

            check_note : str = _price_check_note(
                pack_price_val ,
                float(product.get('Packing Size' , 1) or 1) ,
                product.pop('Printed Unit Price' , 0.0) ,
                product.pop('Line Qty' , 0.0) ,
                product.pop('Line Amount' , 0.0)
            )

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
                'Check' : check_note ,
                'Redundant' : json.dumps(
                    product.get('Redundant' , [])
                )
            }

            processed_items.append(product_dict)

        except Exception as inner_e : 
            st.error(f'Error processing product dictionary : {inner_e}')

    # * Document-level check : the lines must add up to the printed subtotal. A row
    # * misread consistently (price AND amount) slips past the per-row check but
    # * not past this one.
    printed_subtotal : float = 0.0

    try :
        printed_subtotal = float(str(data.get('document_subtotal') or 0).replace(',' , ''))
    except (TypeError , ValueError) :
        printed_subtotal = 0.0

    if printed_subtotal > 0 and line_amounts_sum > 0 :

        if abs(line_amounts_sum - printed_subtotal) > max(0.05 , 0.001 * printed_subtotal) :

            total_note : str = (
                f'⚠ invoice lines add up to {line_amounts_sum:,.2f} but the printed '
                f'subtotal is {printed_subtotal:,.2f} — a price on this invoice was misread'
            )

            for item in processed_items :
                item['Check'] = f'{item["Check"]} ; {total_note}' if item['Check'] else total_note

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

def _match_key(text : Any) -> str :

    # * Loose comparison key : lowercase, letters / digits only.
    return re.sub(r'[^a-z0-9]' , '' , str(text or '').lower())


def _name_tokens(text : Any) -> list[str] :

    # * Words of the name without packing / weight tokens (12X276G , 8(6X79G) , 360G)
    # * so "MUNCHY'S WHEAT CRACKERS 12X276G" -> [munchys , wheat , crackers].
    words : list[str] = re.findall(r'[a-z0-9]+' , str(text or '').lower().replace("'" , ''))

    return [w for w in words if not re.search(r'\d' , w)]


def _is_subsequence(short : str , long : str) -> bool :

    chars : Any = iter(long)

    return all(c in chars for c in short)


def _token_match(a : str , b : str) -> float :

    if a == b or a.rstrip('s') == b.rstrip('s') :
        return 1.0

    # * Initials : H&S ~ HOT & SPICY (one side a single letter).
    if (len(a) == 1) != (len(b) == 1) :
        return 0.8 if a[0] == b[0] else 0.0

    if len(a) == 1 or len(b) == 1 :
        return 0.0

    short , long = sorted((a.rstrip('s') , b.rstrip('s')) , key = len)

    # * Abbreviations : CRK / CRKS ~ CRACKER , PNUT ~ PEANUT , SWICH ~ SANDWICH.
    if len(short) >= 3 and short[0] == long[0] and _is_subsequence(short , long) :
        return 0.8

    if difflib.SequenceMatcher(None , a , b).ratio() >= 0.85 :
        return 0.8

    return 0.0


def _coverage(a : list[str] , b : list[str]) -> float :

    if not a or not b :
        return 0.0

    scores : list[float] = [max(_token_match(t , o) for o in b) for t in a]

    # * Unmatched single letters (the F / P of "F/P") are noise , not evidence.
    kept : list[float] = [
        score for token , score in zip(a , scores)
        if not (len(token) == 1 and score == 0.0)
    ]

    return sum(kept) / len(kept) if kept else 0.0


def _name_similarity(a : list[str] , b : list[str]) -> float :

    # * Both names must explain each other : "MAMEE PREMIUM CURRY NOODLE" fully
    # * contains "MAMEE CURRY" but half its own words are unexplained -> low.
    if not a or not b :
        return 0.0

    # * Brand guard : the leading word (brand) of one name must appear in the
    # * other — LEXUS VEGETABLE ~ MUNCHYS LEXUS CRKS VEGETABLE is fine , but
    # * LEXUS PEANUT BUTTER must never match JULIES PNUT BUTTER.
    if (
        max(_token_match(a[0] , o) for o in b) < 1.0 and
        max(_token_match(b[0] , o) for o in a) < 1.0
    ) :
        return 0.0

    return min(_coverage(a , b) , _coverage(b , a))


def suggest_master_matches(
    pending_rows : list[dict[str , Any]] ,
    master_df : pl.DataFrame
) -> list[str] :

    '''
    For each pending invoice row return the Product Name of the existing master row
    (same supplier) it most likely is, or '' when there is no confident match.

    Order of evidence : identical barcode -> identical loose name -> scored
    candidate (name words + same packing size + same pack price). Each master
    row is suggested at most once. These are SUGGESTIONS shown in the review
    table ; the user confirms or changes them before anything is written.
    '''

    suggestions : list[str] = [''] * len(pending_rows)

    if master_df is None or master_df.is_empty() :
        return suggestions

    master_records : list[dict[str , Any]] = master_df.select(
        [c for c in ['Barcode' , 'Product Name' , 'Packing Size' , 'Pack Price' , 'Supplier'] if c in master_df.columns]
    ).to_dicts()

    used : set[tuple[str , str]] = set()

    def _num(value : Any) -> float :
        try :
            return float(value)
        except (TypeError , ValueError) :
            return 0.0

    for index , row in enumerate(pending_rows) :

        supplier_key : str = _match_key(row.get('Supplier'))

        candidates : list[dict[str , Any]] = [
            m for m in master_records
            if _match_key(m.get('Supplier')) == supplier_key
            and (supplier_key , _match_key(m.get('Product Name'))) not in used
        ]

        if not candidates :
            continue

        best : dict[str , Any] | None = None

        barcode : str = re.sub(r'\D' , '' , str(row.get('Barcode') or ''))

        if barcode :
            best = next(
                (m for m in candidates if re.sub(r'\D' , '' , str(m.get('Barcode') or '')).endswith(barcode[-12 :])
                 and str(m.get('Barcode') or '').strip()) ,
                None
            )

        if best is None :
            name_key : str = _match_key(row.get('Product Name'))
            best = next(
                (m for m in candidates if _match_key(m.get('Product Name')) == name_key) ,
                None
            )

        if best is None :

            row_tokens : list[str] = _name_tokens(row.get('Product Name'))
            row_size : float = _num(row.get('Packing Size'))
            row_price : float = _num(row.get('Pack Price'))

            best_score : float = 0.0

            for m in candidates :

                name_score : float = _name_similarity(row_tokens , _name_tokens(m.get('Product Name')))

                same_size : bool = row_size > 0 and _num(m.get('Packing Size')) == row_size

                master_price : float = _num(m.get('Pack Price'))
                same_price : bool = (
                    row_price > 0 and master_price > 0 and
                    abs(master_price - row_price) <= 0.01 * max(master_price , row_price)
                )

                # * Name must carry real weight on its own ; size / price only
                # * break ties and lift borderline name matches.
                if name_score < 0.6 :
                    continue

                score : float = name_score + (0.15 if same_size else 0.0) + (0.2 if same_price else 0.0)

                if score > best_score :
                    best_score , best = score , m

            if best_score < 0.85 :
                best = None

        if best is not None :
            suggestions[index] = str(best.get('Product Name'))
            used.add((supplier_key , _match_key(best.get('Product Name'))))

    return suggestions
