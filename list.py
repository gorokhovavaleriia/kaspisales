import streamlit as st
import pandas as pd
import plotly.express as px
from pathlib import Path
import requests
from bs4 import BeautifulSoup
import xml.etree.ElementTree as ET
import re
import streamlit.components.v1 as components
import gspread

st.set_page_config(page_title="Аналитика продаж", layout="wide")

# --- ГЛОБАЛЬНЫЕ СТИЛИ ---
st.markdown("""
<style>
/* Заголовок страницы по центру */
h1 { text-align: center; }
.page-subtitle {
    text-align: center;
    color: #64748b;
    font-size: 0.9rem;
    margin-bottom: 8px;
}

/* Заголовок карточки: артикул | название · кнопка двойников */
.card-header {
    display: flex;
    align-items: baseline;
    flex-wrap: wrap;
    gap: 6px;
    margin-bottom: 10px;
}
.article-link {
    font-size: 1.05rem;
    font-weight: 700;
    color: #2563eb;
    text-decoration: none;
    white-space: nowrap;
}
.article-link:hover { text-decoration: underline; }
.article-plain {
    font-size: 1.05rem;
    font-weight: 700;
    color: #1e293b;
    white-space: nowrap;
}
.card-sep { color: #cbd5e1; font-weight: 300; }
.product-name-inline {
    font-size: 0.95rem;
    color: #475569;
}
.sibling-badge {
    font-size: 0.8rem;
    color: #6366f1;
    white-space: nowrap;
}

/* Мини-плитки метрик */
.metric-mini-grid {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 6px 10px;
    margin-bottom: 10px;
}
.metric-mini {
    background: #f8fafc;
    border: 1px solid #e2e8f0;
    border-radius: 8px;
    padding: 6px 10px;
}
.metric-label {
    font-size: 0.68rem;
    color: #94a3b8;
    text-transform: uppercase;
    letter-spacing: 0.04em;
    margin-bottom: 1px;
}
.metric-value-sm {
    font-size: 0.95rem;
    font-weight: 600;
    color: #1e293b;
}
.metric-block { margin-bottom: 8px; }
.metric-value {
    font-size: 1.2rem;
    font-weight: 700;
    color: #1e293b;
}

/* Прибыль */
.profit-positive { color: #16a34a; }
.profit-negative { color: #dc2626; }

/* Бейдж "скорость снижена" */
.badge-warning {
    display: inline-block;
    background: #fef3c7;
    color: #92400e;
    border-radius: 6px;
    padding: 2px 10px;
    font-size: 0.78rem;
    font-weight: 600;
    margin-top: 4px;
}

/* Полоса-заголовок калькулятора */
.calc-header {
    display: flex;
    align-items: center;
    gap: 7px;
    background: #eff6ff;
    border-left: 3px solid #2563eb;
    border-radius: 6px;
    padding: 6px 12px;
    font-size: 0.82rem;
    font-weight: 600;
    color: #1e40af;
    margin-bottom: 8px;
}
.calc-result {
    font-size: 0.92rem;
    color: #334155;
    margin: 3px 0;
}
.calc-result b { color: #1e293b; }
.rec-prices {
    margin-top: 6px;
    font-size: 0.85rem;
    color: #64748b;
}
.rec-prices b { color: #2563eb; }

/* Поля ввода — убрать кнопки +/- и уменьшить */
[data-testid="stNumberInputStepUp"],
[data-testid="stNumberInputStepDown"] {
    display: none !important;
}
[data-testid="stNumberInput"] input {
    font-size: 0.9rem !important;
    padding: 4px 8px !important;
}

/* Кнопка двойников — прижата к названию и стилизована как бейдж */
div[data-testid="stMarkdown"]:has(.card-header) + div[data-testid="stButton"],
div[data-testid="stMarkdown"]:has(.card-header) + div > div[data-testid="stButton"] {
    margin-top: -12px !important;
}
div[data-testid="stMarkdown"]:has(.card-header) + div[data-testid="stButton"] button {
    background: #ede9fe !important;
    border: 1px solid #c4b5fd !important;
    border-radius: 20px !important;
    color: #6d28d9 !important;
    font-size: 0.78rem !important;
    font-weight: 600 !important;
    padding: 2px 12px !important;
    box-shadow: none !important;
    min-height: 0 !important;
    height: 26px !important;
    line-height: 1 !important;
}
div[data-testid="stMarkdown"]:has(.card-header) + div[data-testid="stButton"] button:hover {
    background: #ddd6fe !important;
    border-color: #a78bfa !important;
}

/* Поле поиска — ограничить ширину */
div[data-testid="stSelectbox"] > div {
    max-width: 380px;
}

/* Ввод страницы — узкий */
div[data-testid="stColumns"]:has([data-testid="stNumberInput"]) [data-testid="stNumberInput"] input {
    width: 52px !important;
    text-align: center !important;
}

/* Разделитель между карточками */
.card-divider {
    border: none;
    border-top: 2px solid #e2e8f0;
    margin: 20px 0 16px 0;
}
</style>
""", unsafe_allow_html=True)

st.markdown('<h1>📊 Динамика продаж</h1>', unsafe_allow_html=True)

# --- ОБНОВЛЕНИЕ ДАННЫХ ---
_SHEET_RULES = [
    ("active",       "Active"),
    ("archive",      "Archive"),
    ("stock",        "Stock"),
    ("склад",        "Stock"),
    ("links",        "Links"),
    ("ссылки",       "Links"),
    ("прибыльность", "PnL"),
    ("pnl",          "PnL"),
]

def _detect_sheet(filename: str):
    name = filename.lower()
    for keyword, sheet in _SHEET_RULES:
        if keyword in name:
            return sheet
    return None

@st.cache_resource
def _get_gc(creds_path: str, token_path: str):
    return gspread.oauth(
        credentials_filename=creds_path,
        authorized_user_filename=token_path,
    )

_CREDS_PATH = Path(__file__).resolve().parent / "oauth_credentials.json"
_TOKEN_PATH = Path(__file__).resolve().parent / "token.json"
_GSHEET_ID = "11D3XcCcbgDAG7VapUNFPJP4LWfLbdSyN84ExtzARN6E"

# На Streamlit Cloud файлы не существуют — пишем их из Secrets
if not _CREDS_PATH.exists() and "gsheets_creds" in st.secrets:
    _CREDS_PATH.write_text(st.secrets["gsheets_creds"])
if not _TOKEN_PATH.exists() and "gsheets_token" in st.secrets:
    _TOKEN_PATH.write_text(st.secrets["gsheets_token"])

# col 9 = "Продавать в месяц", col 10 = "Неснижаемый остаток", col 13 = "Комментарий" in "data" sheet
# _COL_PROD_MONTH = 9
# _COL_MIN_STOCK = 10
_COL_COMMENT = 13

def _ensure_gsheet_manual_loaded():
    if 'gsheet_manual' in st.session_state:
        return
    st.session_state.gsheet_manual = {}
    st.session_state.gsheet_row_map = {}
    if not _TOKEN_PATH.exists():
        return
    try:
        gc = _get_gc(str(_CREDS_PATH), str(_TOKEN_PATH))
        sh = gc.open_by_key(_GSHEET_ID)
        ws = sh.worksheet("data")
        rows = ws.get_all_values()
        for i, row in enumerate(rows[1:], start=2):
            if not row or not row[0]:
                continue
            art = str(row[0]).strip()
            comment = str(row[12]).strip() if len(row) > 12 and row[12] else ''
            st.session_state.gsheet_manual[art] = {'comment': comment}
            st.session_state.gsheet_row_map[art] = i
    except Exception:
        pass

def _save_manual_cell(article, col_idx, value):
    if not _TOKEN_PATH.exists():
        st.session_state['_gsheet_save_error'] = "token.json не найден — запусти auth_gsheets.py"
        return
    row_map = st.session_state.get('gsheet_row_map', {})
    art_str = str(article).strip()
    row = row_map.get(art_str)
    if not row:
        # GSheets мог срезать ведущие нули (хранит как число)
        try:
            row = row_map.get(str(int(art_str)))
        except (ValueError, TypeError):
            pass
    if not row:
        st.session_state['_gsheet_save_error'] = f"Артикул {article} не найден в таблице — сначала нажми «Выгрузить данные»"
        return
    try:
        gc = _get_gc(str(_CREDS_PATH), str(_TOKEN_PATH))
        sh = gc.open_by_key(_GSHEET_ID)
        ws = sh.worksheet("data")
        ws.update_cell(row, col_idx, value)
        st.session_state['_gsheet_save_error'] = None
    except Exception as e:
        st.session_state['_gsheet_save_error'] = str(e)

def _on_comment_change(article):
    val = st.session_state.get(f"comment_{article}", '') or ''
    st.session_state.setdefault('gsheet_manual', {}).setdefault(str(article), {})['comment'] = val
    _save_manual_cell(article, _COL_COMMENT, val)

with st.expander("📤 Обновление данных в Google Sheets"):
    _files = st.file_uploader("Загрузи Excel-файлы", type=["xlsx", "xls"],
                               accept_multiple_files=True, key="gsheet_files")
    if _files:
        _plan = []
        _unknown = []
        for f in _files:
            sheet_name = _detect_sheet(f.name)
            if sheet_name:
                _plan.append((f, sheet_name))
            else:
                _unknown.append(f.name)
        if _unknown:
            st.warning("Не распознаны: " + ", ".join(_unknown))
        if _plan:
            st.markdown("**Будет обновлено:**")
            for f, sn in _plan:
                st.markdown(f"- `{f.name}` → лист **{sn}**")
            if st.button("✅ Загрузить в Google Sheets", type="primary"):
                if not _CREDS_PATH.exists():
                    st.error(f"Не найден файл {_CREDS_PATH}. Положи oauth_credentials.json в папку проекта.")
                else:
                    try:
                        gc = _get_gc(str(_CREDS_PATH), str(_TOKEN_PATH))
                        sh = gc.open_by_key(_GSHEET_ID)
                        for f, sheet_name in _plan:
                            with st.spinner(f"Загружаю {f.name} → {sheet_name}…"):
                                f.seek(0)
                                df_up = pd.read_excel(f)
                                df_up = df_up.fillna("").astype(str)
                                try:
                                    ws = sh.worksheet(sheet_name)
                                except gspread.WorksheetNotFound:
                                    ws = sh.add_worksheet(title=sheet_name, rows=1, cols=1)
                                ws.clear()
                                ws.update([df_up.columns.tolist()] + df_up.values.tolist())
                                st.success(f"✅ {sheet_name} обновлён — {len(df_up):,} строк")
                    except Exception as e:
                        st.error(f"Ошибка: {e}")

# --- Состояние сессии ---
if "prev_selected_val" not in st.session_state:
    st.session_state.prev_selected_val = None
if "prev_search_mode" not in st.session_state:
    st.session_state.prev_search_mode = None
if "show_all_mode" not in st.session_state:
    st.session_state.show_all_mode = False

# --- ПАНЕЛЬ ЗАГРУЗКИ ---
# st.sidebar.header("📁 Загрузка данных")
# st.sidebar.write("Прикрепите выгрузки заказов (ArchiveOrders и ActiveOrders)")

project_root = Path(__file__).resolve().parent

default_xml_path = project_root / "ACTIVE.xml" if (project_root / "ACTIVE.xml").exists() else None
# xml_file = st.sidebar.file_uploader("Каталог Kaspi (XML)", type=['xml'])
# selected_xml_file = xml_file if xml_file else default_xml_path
selected_xml_file = default_xml_path

default_uploaded_paths = [project_root / name for name in ["Archive.csv", "Active.csv"] if (project_root / name).exists()]
default_stock_path = project_root / "Stock.csv" if (project_root / "Stock.csv").exists() else None
default_links_path = project_root / "Links.csv" if (project_root / "Links.csv").exists() else None
default_pnl_path = next((project_root / n for n in ["PnL.csv", "pnl.csv", "Pnl.csv"] if (project_root / n).exists()), None)

# uploaded_files = st.sidebar.file_uploader("Выберите один или несколько CSV файлов", type=['csv'], accept_multiple_files=True)
# stock_file = st.sidebar.file_uploader("Остатки (CSV)", type=['csv'])
# links_file = st.sidebar.file_uploader("Ссылки", type=['csv'])

selected_uploaded_files = default_uploaded_paths
selected_stock_file = default_stock_path
selected_links_file = default_links_path
selected_pnl_file = default_pnl_path


@st.cache_data(show_spinner=False, ttl=3600)
def fetch_kaspi_data(url):
    if not url or pd.isna(url):
        return None, None
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept-Language": "ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7"
    }
    try:
        response = requests.get(url, headers=headers, timeout=5)
        if response.status_code != 200:
            return None, None
        soup = BeautifulSoup(response.text, 'html.parser')
        img_tag = soup.find('img', class_='item__slider-pic')
        img_src = img_tag['src'] if img_tag and 'src' in img_tag.attrs else None
        sellers_table = soup.select_one('table.sellers.table')
        sellers_df = None
        if sellers_table:
            tables = pd.read_html(str(sellers_table))
            if tables:
                sellers_df = tables[0]
        return img_src, sellers_df
    except Exception:
        return None, None


def resolvefile_source(file):
    if hasattr(file, "seek"):
        file.seek(0)
        return file
    return Path(file)


@st.cache_data
def process_uploaded_files(files):
    dfs = []
    for file in files:
        try:
            df = pd.read_csv(file)
            dfs.append(df)
        except Exception as e:
            st.error(f"Ошибка при чтении файла {file.name}: {e}")
            return pd.DataFrame()
    if not dfs:
        return pd.DataFrame()
    df = pd.concat(dfs, ignore_index=True)
    df.columns = df.columns.str.strip()
    df['Артикул'] = df['Артикул'].astype(str).str.strip()
    if 'Название в системе продавца' in df.columns:
        df['Название в системе продавца'] = df['Название в системе продавца'].fillna('Не указано').astype(str).str.strip()
    df['Дата поступления заказа'] = pd.to_datetime(df['Дата поступления заказа'], format='%d.%m.%Y', errors='coerce')
    df['Количество'] = pd.to_numeric(df['Количество'], errors='coerce').fillna(0)
    df = df.dropna(subset=['Дата поступления заказа', 'Артикул'])
    return df


@st.cache_data
def process_xml_prices(file):
    if file is None:
        return {}, {}, {}
    price_dict = {}
    names_dict = {}
    stock_dict = {}
    try:
        source = resolvefile_source(file)
        tree = ET.parse(source)
        root = tree.getroot()
        ns = {'kaspi': 'kaspiShopping'}
        offers = root.findall('.//kaspi:offer', ns)
        if not offers:
            offers = root.findall('.//offer')
        for offer in offers:
            sku = offer.get('sku')
            if not sku:
                continue
            sku = str(sku).strip()

            model_node = offer.find('.//kaspi:model', ns) or offer.find('.//model')
            if model_node is None:
                for child in offer.iter():
                    if child.tag == 'model' or child.tag.endswith('}model'):
                        model_node = child
                        break
            model_name = model_node.text.strip() if model_node is not None and model_node.text else sku
            names_dict[sku] = model_name

            avail_node = offer.find('.//kaspi:availabilities/kaspi:availability', ns) or offer.find('.//availabilities/availability')
            if avail_node is None:
                for child in offer.iter():
                    if child.tag == 'availability' or child.tag.endswith('}availability'):
                        avail_node = child
                        break
            if avail_node is not None:
                try:
                    stock_dict[sku] = float(avail_node.get('stockCount', 0))
                except (ValueError, TypeError):
                    stock_dict[sku] = 0

            price_node = offer.find('.//kaspi:cityprices/kaspi:cityprice[@cityId="710000000"]', ns)
            if price_node is None:
                price_node = offer.find('.//cityprices/cityprice[@cityId="710000000"]')
            if price_node is not None and price_node.text:
                try:
                    price = float(price_node.text)
                    price_dict[sku] = price
                    base_sku = sku.split('_')[0]
                    if base_sku != sku:
                        price_dict.setdefault(base_sku, price)
                except ValueError:
                    pass
    except Exception:
        pass
    return price_dict, names_dict, stock_dict


@st.cache_data
def process_stock(file):
    try:
        source = resolvefile_source(file)
        raw_df = pd.read_csv(source, header=None, encoding='utf-8-sig', sep=None, engine='python')
        header_idx = None
        for idx, row in raw_df.iterrows():
            row_values = [str(v).strip().lower() for v in row.tolist() if pd.notna(v)]
            if any(col in row_values for col in ['артикул', 'наименование', 'остаток', 'себестоимость']):
                header_idx = idx
                break
        if header_idx is None:
            return None
        df_stock = raw_df.iloc[header_idx + 1:].copy()
        df_stock.columns = raw_df.iloc[header_idx]
        df_stock.columns = [str(col).strip() for col in df_stock.columns]
        name_col = next((col for col in df_stock.columns if 'наименование' in str(col).lower()), None)
        stock_col = next((col for col in df_stock.columns if 'остаток' in str(col).lower()), None)
        reserve_col = next((col for col in df_stock.columns if 'резерв' in str(col).lower()), None)
        cost_col = next((col for col in df_stock.columns if 'себестоимость' in str(col).lower()), None)
        article_col = next((col for col in df_stock.columns if 'артикул' in str(col).lower()), None)
        price_col = next((col for col in df_stock.columns if 'цена продажи' in str(col).lower()), None)
        days_col = next((col for col in df_stock.columns if 'дней' in str(col).lower()), None)
        if not name_col or not article_col:
            return None
        needed_cols = [col for col in [article_col, name_col, stock_col, reserve_col, cost_col, price_col, days_col] if col is not None]
        df_stock = df_stock[needed_cols].copy()
        rename_map = {article_col: 'Артикул', name_col: 'Наименование', stock_col: 'Остаток',
                      reserve_col: 'Резерв', cost_col: 'Себестоимость', price_col: 'Цена продажи'}
        if days_col:
            rename_map[days_col] = 'Дней на складе'
        df_stock = df_stock.rename(columns=rename_map)
        df_stock = df_stock.dropna(subset=['Наименование'])
        df_stock['Наименование_clean'] = df_stock['Наименование'].astype(str).str.strip().str.lower().str.replace(r'\s+', ' ', regex=True)
        df_stock['Артикул'] = df_stock['Артикул'].astype(str).str.strip()
        for col in ['Остаток', 'Резерв', 'Себестоимость', 'Цена продажи', 'Дней на складе']:
            if col in df_stock.columns:
                df_stock[col] = pd.to_numeric(df_stock[col].astype(str).str.replace(',', '.'), errors='coerce').fillna(0)
        return df_stock
    except Exception:
        return None


@st.cache_data
def process_pnl(file):
    errors = []
    try:
        source = resolvefile_source(file)
        raw_df = None
        for enc in ('utf-8-sig', 'utf-8', 'cp1251'):
            for sep in (None, ';', ',', '\t'):
                try:
                    source = resolvefile_source(file)
                    raw_df = pd.read_csv(source, header=None, encoding=enc,
                                         sep=sep, engine='python')
                    if raw_df.shape[1] > 1:
                        break
                except Exception as e:
                    errors.append(f"enc={enc} sep={sep}: {e}")
            if raw_df is not None and raw_df.shape[1] > 1:
                break

        if raw_df is None or raw_df.shape[1] <= 1:
            return f"PARSE_ERROR: не удалось прочитать файл. Попытки: {errors}"

        # Ищем строку с "себестоимость" (sub-header) и строку выше с "артикул" (parent-header)
        parent_idx = None
        sub_idx = None
        for idx, row in raw_df.iterrows():
            row_values = [str(v).strip().lower() for v in row.tolist() if pd.notna(v)]
            if 'себестоимость' in row_values:
                sub_idx = idx
                break
            if any(col in row_values for col in ['артикул', 'наименование']):
                parent_idx = idx

        if sub_idx is None:
            sample = raw_df.head(15).to_string()
            return f"HEADER_NOT_FOUND: Первые строки:\n{sample}"

        # Объединяем два уровня заголовка: для каждой позиции берём sub если есть, иначе parent
        sub_row = raw_df.iloc[sub_idx].tolist()
        parent_row = raw_df.iloc[parent_idx].tolist() if parent_idx is not None else [None] * len(sub_row)
        combined_cols = []
        for ph, sh in zip(parent_row, sub_row):
            sh_str = str(sh).strip() if pd.notna(sh) else ''
            ph_str = str(ph).strip() if pd.notna(ph) else ''
            combined_cols.append(sh_str if sh_str and sh_str != 'nan' else (ph_str if ph_str and ph_str != 'nan' else 'nan'))

        article_col_idx = next((i for i, c in enumerate(combined_cols) if str(c).lower() == 'код'), None)
        cost_col_idx = next((i for i, c in enumerate(combined_cols) if 'себестоимость' in str(c).lower()), None)

        if article_col_idx is None or cost_col_idx is None:
            return f"COLS_NOT_FOUND: колонки={combined_cols}"

        data = raw_df.iloc[sub_idx + 1:]
        df_pnl = pd.DataFrame({
            'Артикул': data.iloc[:, article_col_idx].values,
            'Себестоимость': data.iloc[:, cost_col_idx].values,
        })
        df_pnl = df_pnl.dropna(subset=['Артикул'])
        df_pnl['Артикул'] = df_pnl['Артикул'].astype(str).str.strip()
        df_pnl['Себестоимость'] = pd.to_numeric(
            df_pnl['Себестоимость'].astype(str).str.replace(',', '.'), errors='coerce'
        ).fillna(0)
        df_pnl = df_pnl[df_pnl['Артикул'].str.len() > 0]
        return df_pnl.drop_duplicates(subset=['Артикул'])
    except Exception as e:
        return f"EXCEPTION: {e}"


@st.cache_data
def process_links(file):
    try:
        source = resolvefile_source(file)
        df = pd.read_csv(source, encoding='utf-8-sig')
        df.columns = df.columns.str.strip()
        if 'Артикул' in df.columns and 'Ссылка' in df.columns:
            links_df = df[['Артикул', 'Ссылка']].copy()
        elif len(df.columns) >= 4:
            links_df = pd.DataFrame({
                'Артикул': df.iloc[:, 0].astype(str).str.strip(),
                'Ссылка': df.iloc[:, 3].astype(str).str.strip()
            })
        else:
            return pd.DataFrame(columns=['Артикул', 'Ссылка'])
        links_df['Артикул'] = links_df['Артикул'].astype(str).str.strip()
        links_df['Ссылка'] = links_df['Ссылка'].astype(str).str.strip()
        links_df = links_df[links_df['Артикул'] != '']
        links_df = links_df[links_df['Ссылка'] != '']
        return links_df.drop_duplicates(subset=['Артикул'])
    except Exception:
        return pd.DataFrame(columns=['Артикул', 'Ссылка'])


@st.cache_data
def build_products_database(df, stock_df, links_df, xml_prices_dict, xml_names_dict, xml_stock_dict, pnl_df, thirty_days_ago, max_date):
    records = []
    daily_sales_dict = {}
    unique_articles = df['Артикул'].unique()
    seven_day_start = max_date - pd.Timedelta(days=9)
    seven_day_end = seven_day_start + pd.Timedelta(days=6)
    yesterday = max_date - pd.Timedelta(days=1)

    for article in unique_articles:
        product_df = df[df['Артикул'] == article]
        product_name = "Не указано"
        if 'Название в системе продавца' in product_df.columns:
            product_name = product_df['Название в системе продавца'].iloc[0]
        prod_name_clean = str(product_name).strip().lower()

        stock_info = "Это комплект"
        cost_info = "Н/Д"
        qty = 0
        cost = 0
        ms_price = 0
        days_on_stock = 10000

        if stock_df is not None:
            match = stock_df[stock_df['Наименование_clean'] == prod_name_clean]
            if match.empty:
                xml_model = xml_names_dict.get(str(article), '')
                if xml_model and xml_model != str(article):
                    xml_name_clean = re.sub(r'\s+', ' ', str(xml_model).strip().lower())
                    match = stock_df[stock_df['Наименование_clean'] == xml_name_clean]
            if not match.empty:
                row = match.iloc[0]
                qty = row['Остаток'] - row['Резерв']
                stock_info = f"{int(qty)} шт."
                cost_info = f"{row['Себестоимость']:,.2f} ₸"
                cost = row['Себестоимость']
                ms_price = row['Цена продажи']
                if 'Дней на складе' in row.index:
                    days_on_stock = int(row['Дней на складе']) if pd.notna(row['Дней на складе']) else 10000
            else:
                xml_qty = xml_stock_dict.get(str(article), 0)
                qty = int(xml_qty) if xml_qty else 0
                stock_info = f"{qty} шт." if qty else "0 шт."
            if qty <= 0 and cost == 0 and pnl_df is not None:
                pnl_match = pnl_df[pnl_df['Артикул'] == str(article).strip()]
                if not pnl_match.empty:
                    cost = pnl_match.iloc[0]['Себестоимость']
                    cost_info = f"{cost:,.2f} ₸"
        else:
            stock_info = "0"

        link_url = None
        if links_df is not None and not links_df.empty:
            l_match = links_df[links_df['Артикул'] == article]
            if not l_match.empty:
                link_url = l_match.iloc[0]['Ссылка']

        recent_sales_df = product_df[product_df['Дата поступления заказа'] >= thirty_days_ago]
        total_sold_30_days = int(recent_sales_df['Количество'].sum())
        totalrevenue = int(recent_sales_df['Сумма'].sum())

        seven_day_sales_df = product_df[
            (product_df['Дата поступления заказа'] >= seven_day_start) &
            (product_df['Дата поступления заказа'] <= seven_day_end)
        ]
        total_sold_7_days = int(seven_day_sales_df['Количество'].sum())
        avgsalespeed = total_sold_7_days / 7 if total_sold_7_days > 0 else 0

        today_and_yesterday_sales_df = product_df[product_df['Дата поступления заказа'] == yesterday]
        avgsalesyesterday = int(today_and_yesterday_sales_df['Количество'].sum())

        mark = True
        if int(qty) <= 0:
            mark = False
        speed_dropped = (avgsalesyesterday < avgsalespeed) and mark

        if cost_info != "Н/Д" and total_sold_30_days > 0:
            avg_price = totalrevenue / total_sold_30_days
            calc_delivery = delivery_cost(avg_price, 1) * total_sold_30_days
            profit = totalrevenue * 0.845 - cost * total_sold_30_days - calc_delivery
        else:
            profit = 0

        product_sales_by_day = product_df.groupby('Дата поступления заказа')['Количество'].sum().sort_index()
        if not product_sales_by_day.empty:
            date_range = pd.date_range(
                start=product_sales_by_day.index.min(),
                end=product_sales_by_day.index.max(),
                freq='D'
            )
            revenue_by_day = product_df.groupby('Дата поступления заказа')['Сумма'].sum()
            daily_sales = product_sales_by_day.reindex(date_range, fill_value=0).reset_index()
            daily_sales.columns = ['Дата поступления заказа', 'Количество']
            daily_sales['Средняя_цена'] = daily_sales['Дата поступления заказа'].map(
                lambda d: round(revenue_by_day.get(d, 0) / product_sales_by_day.get(d, 1)) if product_sales_by_day.get(d, 0) > 0 else 0
            )
        else:
            daily_sales = pd.DataFrame(columns=['Дата поступления заказа', 'Количество', 'Средняя_цена'])
        daily_sales_dict[article] = daily_sales

        current_price = xml_prices_dict.get(article, None)
        price_info = f"{current_price:,.0f}" if current_price is not None else "Н/Д"

        price_diff_percent = None
        if current_price is not None and ms_price not in (None, 0) and pd.notna(ms_price):
            price_diff_percent = abs((current_price - ms_price) / ms_price * 100)

        records.append({
            'Артикул': article,
            'Название': product_name,
            'sort_name': str(product_name).lower(),
            'Ссылка': link_url,
            'Остаток_инфо': stock_info,
            'Остаток количество': qty,
            'Себестоимость_инфо': cost_info,
            'Cебестоимсость цена': cost,
            'Продано_30_дней': total_sold_30_days,
            'Продано_7_дней': total_sold_7_days,
            'Продано_вчера': avgsalesyesterday,
            'Прибыль': profit,
            'Скорость_продаж': avgsalespeed,
            'Снижение_скорости': speed_dropped,
            'Цена в мс': ms_price,
            'Цена в xml': price_info,
            'Разница_цен_%': price_diff_percent,
            'Дней на складе': days_on_stock
        })

    # Добавляем артикулы из XML у которых не было продаж
    orders_articles = set(str(a).strip() for a in unique_articles)
    for sku, model_name in xml_names_dict.items():
        if sku in orders_articles:
            continue
        prod_name_clean = re.sub(r'\s+', ' ', str(model_name).strip().lower())
        stock_info = "0 шт."
        cost_info = "Н/Д"
        qty = 0
        cost = 0
        ms_price = 0
        days_on_stock = 10000
        if stock_df is not None:
            match = stock_df[stock_df['Наименование_clean'] == prod_name_clean]
            if not match.empty:
                row = match.iloc[0]
                qty = row['Остаток'] - row['Резерв']
                stock_info = f"{int(qty)} шт."
                cost_info = f"{row['Себестоимость']:,.2f} ₸"
                cost = row['Себестоимость']
                ms_price = row['Цена продажи']
                if 'Дней на складе' in row.index:
                    days_on_stock = int(row['Дней на складе']) if pd.notna(row['Дней на складе']) else 10000
            else:
                xml_qty = xml_stock_dict.get(sku, 0)
                qty = int(xml_qty) if xml_qty else 0
                stock_info = f"{qty} шт." if qty else "0 шт."
            if qty <= 0 and cost == 0 and pnl_df is not None:
                pnl_match = pnl_df[pnl_df['Артикул'] == str(sku).strip()]
                if not pnl_match.empty:
                    cost = pnl_match.iloc[0]['Себестоимость']
                    cost_info = f"{cost:,.2f} ₸"
        link_url = None
        if links_df is not None and not links_df.empty:
            l_match = links_df[links_df['Артикул'] == sku]
            if not l_match.empty:
                link_url = l_match.iloc[0]['Ссылка']
        daily_sales_dict[sku] = pd.DataFrame(columns=['Дата поступления заказа', 'Количество'])
        current_price = xml_prices_dict.get(sku, None)
        price_info = f"{current_price:,.0f}" if current_price is not None else "Н/Д"
        price_diff_percent = None
        if current_price is not None and ms_price not in (None, 0) and pd.notna(ms_price):
            price_diff_percent = abs((current_price - ms_price) / ms_price * 100)
        records.append({
            'Артикул': sku,
            'Название': model_name,
            'sort_name': str(model_name).lower(),
            'Ссылка': link_url,
            'Остаток_инфо': stock_info,
            'Остаток количество': qty,
            'Себестоимость_инфо': cost_info,
            'Cебестоимсость цена': cost,
            'Продано_30_дней': 0,
            'Продано_7_дней': 0,
            'Продано_вчера': 0,
            'Прибыль': 0,
            'Скорость_продаж': 0,
            'Снижение_скорости': False,
            'Цена в мс': ms_price,
            'Цена в xml': price_info,
            'Разница_цен_%': price_diff_percent,
            'Дней на складе': days_on_stock
        })


    return pd.DataFrame(records), daily_sales_dict


def render_pagination_controls(current_page, total_pages, position="middle"):
    col_prev, col_page, col_input, col_next = st.columns([2, 2, 1, 2])
    with col_prev:
        if st.button("← Назад", key=f"prev_page_{position}_{current_page}", use_container_width=True, disabled=current_page == 1):
            st.session_state.all_articles_page = current_page - 1
            st.rerun()
    with col_page:
        st.markdown(f"<div style='text-align:center; padding-top:6px;'><b>Стр. {current_page} из {total_pages}</b></div>", unsafe_allow_html=True)
    with col_input:
        new_page = st.number_input(
            "Страница",
            min_value=1,
            max_value=total_pages,
            value=current_page,
            step=1,
            label_visibility="collapsed",
            key=f"page_number_input_{position}_{current_page}",
        )
        if new_page != current_page:
            st.session_state.all_articles_page = int(new_page)
            st.rerun()
    with col_next:
        if st.button("Вперёд →", key=f"next_page_{position}_{current_page}", use_container_width=True, disabled=current_page == total_pages):
            st.session_state.all_articles_page = current_page + 1
            st.rerun()


def delivery_cost(price, weight):
    if price < 1000:
        return 57
    elif 1000 <= price < 3000:
        return 173
    elif 3000 <= price < 5000:
        return 231
    elif 5000 <= price < 10000:
        return 925
    else:
        return 1705 if weight < 5 else 1971


def fmt_price(val):
    """Форматирует число как цену в тенге без дублирования знака."""
    try:
        return f"{int(float(val)):,} ₸".replace(",", " ")
    except (ValueError, TypeError):
        return "Н/Д"


# --- ОСНОВНАЯ ЛОГИКА ---
if selected_uploaded_files:
    df = process_uploaded_files(selected_uploaded_files)
    stock_df = process_stock(selected_stock_file) if selected_stock_file else None
    links_df = process_links(selected_links_file) if selected_links_file else None
    pnl_result = process_pnl(selected_pnl_file) if selected_pnl_file else None
    pnl_df = pnl_result if isinstance(pnl_result, pd.DataFrame) else None
    if not df.empty:
        df['Дата поступления заказа'] = pd.to_datetime(df['Дата поступления заказа'])
        max_date = df['Дата поступления заказа'].max()
        thirty_days_ago = max_date - pd.Timedelta(days=30)
        x_axis_start = thirty_days_ago
        x_axis_end = max_date + pd.Timedelta(days=1)

        xml_prices_dict, xml_names_dict, xml_stock_dict = process_xml_prices(selected_xml_file) if selected_xml_file else ({}, {}, {})
        products_db, daily_sales_dict = build_products_database(df, stock_df, links_df, xml_prices_dict, xml_names_dict, xml_stock_dict, pnl_df, thirty_days_ago, max_date)
        _ensure_gsheet_manual_loaded()

        st.markdown(f'<div class="page-subtitle">🗓️ Метрика за последние 30 дней: с <b>{thirty_days_ago.strftime("%d.%m.%Y")}</b> по <b>{max_date.strftime("%d.%m.%Y")}</b></div>', unsafe_allow_html=True)
        st.markdown("---")

        col_search, col_btn = st.columns([2, 1])
        with col_search:
            search_mode = st.radio("Искать товар по:", ["Артикулу", "Названию в системе продавца"], horizontal=True)
            if search_mode == "Артикулу":
                unique_options = sorted(products_db['Артикул'].unique())
                selected_val = st.selectbox("Выберите артикул:", options=unique_options)
            else:
                unique_options = sorted(products_db['Название'].unique())
                selected_val = st.selectbox("Выберите название:", options=unique_options)
            speed_drop_only = st.checkbox("⚠️ Только со снижением скорости продаж", value=False)
            price_diff_only = st.checkbox("💸 Только с расхождением цены MS и текущей > 3%", value=False)
            stock_only = st.checkbox("📦 Только с остатком > 0", value=False)
            new_only = st.checkbox("🆕 Только новые товары (< 10 дней)", value=False)
            sort_by_profit = st.checkbox("💰 Сортировать по прибыли (сначала выгодные)", value=False)
        with col_btn:
            st.write("")
            st.write("")
            if st.button("Показать продажи по всем карточкам", use_container_width=True):
                st.session_state.show_all_mode = True
                st.session_state.all_articles_page = 1
            st.write("")
            if st.button("📊 Выгрузить данные в Google Sheets", use_container_width=True):
                if not _TOKEN_PATH.exists():
                    st.error("Сначала авторизуйся: запусти python3 auth_gsheets.py в терминале")
                else:
                    try:
                        with st.spinner("Выгружаю данные…"):
                            _exp = products_db[['Артикул', 'Название', 'Cебестоимсость цена', 'Остаток количество', 'Продано_30_дней', 'Прибыль']].copy()
                            _exp.rename(columns={
                                'Название': 'Название в системе продавца',
                                'Cебестоимсость цена': 'Себестоимость',
                                'Остаток количество': 'Остаток',
                                'Продано_30_дней': 'Продано за 30 дней',
                                'Прибыль': 'Прибыль за 30 дней',
                            }, inplace=True)
                            _exp['Общая себестоимость'] = (_exp['Остаток'] * _exp['Себестоимость']).round(2)
                            _denom = _exp['Продано за 30 дней'] * _exp['Себестоимость']
                            _exp['Рентабельность, %'] = (_exp['Прибыль за 30 дней'] / _denom.replace(0, float('nan')) * 100).round(1).fillna(0)
                            _exp['Продавать в месяц'] = ''
                            _exp['Неснижаемый остаток'] = ''
                            _exp['Перестать закупать стоит'] = ''
                            _exp['Поменять перестать закупать'] = ''
                            _manual_cache = st.session_state.get('gsheet_manual', {})
                            _exp['Комментарий'] = _exp['Артикул'].astype(str).map(
                                lambda a: _manual_cache.get(a, {}).get('comment', '')
                            )
                            _exp = _exp[['Артикул', 'Название в системе продавца', 'Себестоимость', 'Остаток',
                                         'Общая себестоимость', 'Продано за 30 дней', 'Прибыль за 30 дней',
                                         'Рентабельность, %', 'Продавать в месяц', 'Неснижаемый остаток',
                                         'Перестать закупать стоит', 'Поменять перестать закупать', 'Комментарий']]
                            _exp = _exp.fillna('').astype(str)
                            gc = _get_gc(str(_CREDS_PATH), str(_TOKEN_PATH))
                            sh = gc.open_by_key(_GSHEET_ID)
                            try:
                                ws = sh.worksheet("data")
                            except gspread.WorksheetNotFound:
                                ws = sh.add_worksheet(title="data", rows=1, cols=1)
                            ws.clear()
                            ws.update([_exp.columns.tolist()] + _exp.values.tolist(), value_input_option='RAW')
                            st.session_state.pop('gsheet_manual', None)
                            st.session_state.pop('gsheet_row_map', None)
                        st.success(f"✅ Выгружено {len(_exp):,} артикулов на лист 'data'")
                    except Exception as e:
                        st.error(f"Ошибка: {e}")

        if st.session_state.prev_selected_val is not None:
            if (st.session_state.prev_selected_val != selected_val) or (st.session_state.prev_search_mode != search_mode):
                st.session_state.show_all_mode = False

        st.session_state.prev_selected_val = selected_val
        st.session_state.prev_search_mode = search_mode

        st.markdown("---")

        filtered_db = products_db.copy()
        if speed_drop_only:
            filtered_db = filtered_db[filtered_db['Снижение_скорости'] == True]
        if price_diff_only:
            filtered_db = filtered_db[
                (filtered_db['Разница_цен_%'].notna()) &
                (filtered_db['Разница_цен_%'] > 3)
            ]
        if stock_only:
            filtered_db = filtered_db[filtered_db['Остаток количество'] > 0]
        if new_only:
            filtered_db = filtered_db[(filtered_db['Дней на складе'] < 10) & (filtered_db['Остаток количество'] > 0)].sort_values('sort_name')

        show_all_mode = st.session_state.get("show_all_mode", False)
        page_size = 15
        current_page = st.session_state.get("all_articles_page", 1)
        total_pages = 1
        articles_to_show = []

        if show_all_mode:
            sorted_db = filtered_db.sort_values('Прибыль', ascending=False) if sort_by_profit else filtered_db.sort_values(['sort_name', 'Артикул'])
            all_articles = sorted_db['Артикул'].tolist()
            total_pages = max(1, (len(all_articles) + page_size - 1) // page_size)
            current_page = max(1, min(current_page, total_pages))
            st.session_state.all_articles_page = current_page
            start_idx = (current_page - 1) * page_size
            end_idx = start_idx + page_size
            articles_to_show = all_articles[start_idx:end_idx]
            render_pagination_controls(current_page, total_pages, position="top")
            st.markdown('<hr class="card-divider">', unsafe_allow_html=True)
        else:
            if search_mode == "Артикулу":
                final_db = filtered_db[filtered_db['Артикул'] == selected_val]
            else:
                final_db = filtered_db[filtered_db['Название'] == selected_val]
            articles_to_show = final_db['Артикул'].tolist()

        # --- ОТРИСОВКА ---
        name_to_articles = products_db.groupby('Название')['Артикул'].apply(list).to_dict()
        duplicate_names = {name: arts for name, arts in name_to_articles.items() if len(arts) > 1}

        articles_set = set(articles_to_show)
        render_list = []
        already_as_sibling = set()

        for art in articles_to_show:
            render_list.append((art, False))
            pname = products_db[products_db['Артикул'] == art].iloc[0]['Название']
            if pname in duplicate_names and st.session_state.get(f"siblings_{art}", False):
                for sib in duplicate_names[pname]:
                    if sib != art and sib not in articles_set and sib not in already_as_sibling:
                        render_list.append((sib, True))
                        already_as_sibling.add(sib)

        for article, is_sibling in render_list:
            row_data = products_db[products_db['Артикул'] == article].iloc[0]
            product_name = row_data['Название']
            link_url = row_data['Ссылка']
            stock_info = row_data['Остаток_инфо']
            quantity = row_data['Остаток количество']
            cost_info = row_data['Себестоимость_инфо']
            cost = row_data['Cебестоимсость цена']
            total_sold_30_days = row_data['Продано_30_дней']
            total_sold_7_days = row_data['Продано_7_дней']
            avgsalesyesterday = row_data['Продано_вчера']
            profit = row_data['Прибыль']
            speed_dropped = row_data['Снижение_скорости']
            ms_price = row_data['Цена в мс']
            current_price_str = row_data['Цена в xml']
            price_diff_percent = row_data['Разница_цен_%']
            days_on_stock = row_data.get('Дней на складе', 10000)
            daily_sales = daily_sales_dict.get(article, pd.DataFrame(columns=['Дата поступления заказа', 'Количество']))

            price_to_calc = int(xml_prices_dict.get(str(article).strip(), 0) or 0)

            # ---- КАРТОЧКА ТОВАРА ----
            has_siblings = product_name in duplicate_names and (speed_drop_only or price_diff_only) and not is_sibling
            if has_siblings:
                sibling_count = len(duplicate_names[product_name]) - 1
                is_exp = st.session_state.get(f"siblings_{article}", False)
                count_word = "двойник" if sibling_count == 1 else "двойника" if sibling_count <= 4 else "двойников"
                sibling_hint = f' &nbsp;<span class="sibling-badge">👥 {sibling_count} {count_word}</span>'
            else:
                sibling_hint = ""

            if link_url:
                article_html = f'<a class="article-link" href="{link_url}" target="_blank">{article}</a>'
            else:
                article_html = f'<span class="article-plain">{article}</span>'

            if is_sibling:
                name_html = f'<span class="card-sep">|</span> <span class="product-name-inline"><i>↩</i> {product_name}</span>'
            else:
                name_html = f'<span class="card-sep">|</span> <span class="product-name-inline">{product_name}</span>'

            components.html(f"""
            <style>
            body{{margin:0;padding:0;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;}}
            .card-header{{display:flex;align-items:baseline;flex-wrap:wrap;gap:6px;margin:0;}}
            .article-link{{font-size:1.05rem;font-weight:700;color:#2563eb;text-decoration:none;white-space:nowrap;}}
            .article-link:hover{{text-decoration:underline;}}
            .article-plain{{font-size:1.05rem;font-weight:700;color:#1e293b;white-space:nowrap;}}
            .card-sep{{color:#cbd5e1;font-weight:300;}}
            .product-name-inline{{font-size:0.95rem;color:#475569;}}
            .copy-btn{{cursor:pointer;font-size:0.8rem;color:#cbd5e1;margin-left:3px;border:none;background:none;padding:0;line-height:1;}}
            .copy-btn:hover{{color:#64748b;}}
            </style>
            <div class="card-header">
                {article_html}
                <button class="copy-btn" title="Скопировать артикул" onclick="copyArt(this)">⧉</button>
                {name_html}
            </div>
            <script>
            function copyArt(btn) {{
                var el = document.createElement('textarea');
                el.value = '{article}';
                el.style.position = 'fixed';
                el.style.opacity = '0';
                document.body.appendChild(el);
                el.select();
                try {{ document.execCommand('copy'); }} catch(e) {{}}
                document.body.removeChild(el);
                btn.textContent = '✓';
                setTimeout(function() {{ btn.textContent = '⧉'; }}, 1200);
            }}
            </script>
            """, height=36, scrolling=False)
            if has_siblings:
                arrow = "▲" if is_exp else "▼"
                if st.button(f"👥 {sibling_count} {count_word} {arrow}", key=f"name_btn_{article}"):
                    st.session_state[f"siblings_{article}"] = not is_exp
                    st.rerun()

            # --- Основные три колонки ---
            col1, col2, col3 = st.columns([1, 1, 2])

            with col1:
                profit_class = "profit-positive" if profit >= 0 else "profit-negative"
                profit_sign = "+" if profit > 0 else ""
                st.markdown(f"""
                <div class="metric-mini-grid">
                    <div class="metric-mini">
                        <div class="metric-label">Себестоимость</div>
                        <div class="metric-value-sm">{cost_info}</div>
                    </div>
                    <div class="metric-mini">
                        <div class="metric-label">🏷️ Цена МС</div>
                        <div class="metric-value-sm">{fmt_price(ms_price)}</div>
                    </div>
                    <div class="metric-mini" title="{'На складе: ' + f'{int(quantity * cost):,} ₸'.replace(',', ' ') if cost and quantity else ''}">
                        <div class="metric-label">Остаток</div>
                        <div class="metric-value-sm">{stock_info}</div>
                    </div>
                    <div class="metric-mini" style="{'background:#fff1f2;border-color:#fca5a5;' if pd.notna(price_diff_percent) and price_diff_percent > 3 else ''}">
                        <div class="metric-label">🛒 Цена Kaspi{'  ⚠️ ' + str(round(price_diff_percent)) + '%' if pd.notna(price_diff_percent) and price_diff_percent > 3 else ''}</div>
                        <div class="metric-value-sm" style="{'color:#dc2626;' if pd.notna(price_diff_percent) and price_diff_percent > 3 else ''}">{current_price_str} ₸</div>
                    </div>
                    <div class="metric-mini">
                        <div class="metric-label">Продано за 30 дней</div>
                        <div class="metric-value-sm">{total_sold_30_days} шт.</div>
                    </div>
                    <div class="metric-mini">
                        <div class="metric-label">Дней на складе</div>
                        <div class="metric-value-sm">{"—" if days_on_stock == 10000 else days_on_stock}</div>
                    </div>
                </div>
                <div class="metric-block">
                    <div class="metric-label">Прибыль (30 дней)</div>
                    <div class="metric-value {profit_class}">{profit_sign}{round(profit):,} ₸</div>
                </div>
                """, unsafe_allow_html=True)
                if speed_dropped:
                    st.markdown('<div class="badge-warning">⚠️ Скорость снижена</div>', unsafe_allow_html=True)

            with col2:
                st.markdown('<div class="calc-header">💰 Калькулятор цены</div>', unsafe_allow_html=True)

                entered_weight = 0
                price_key = f"price_{article}"
                entered_price = st.number_input(
                    "Введи цену",
                    min_value=0,
                    step=1,
                    value=price_to_calc,
                    key=price_key,
                )

                if entered_price is not None:
                    price_to_calc = entered_price if entered_price > 0 else price_to_calc
                    if entered_price > 10000:
                        entered_weight = st.number_input(
                            "Вес товара (кг)",
                            min_value=0,
                            step=1,
                            key=f"вес_{article}",
                        )

                cost_num = int(cost) if cost != "Н/Д" else 0
                p_profit = price_to_calc * 0.845 - cost_num - delivery_cost(price_to_calc, entered_weight if price_to_calc > 10000 else 1)

                if price_to_calc > 0:
                    margin = p_profit / price_to_calc * 100
                    rent = p_profit / cost_num * 100 if cost_num > 0 else 0
                else:
                    margin = 0
                    rent = 0

                rec_price1 = (cost_num * 1.3 + delivery_cost(price_to_calc, entered_weight if price_to_calc > 10000 else 1)) / 0.845
                rec_price2 = (cost_num + delivery_cost(price_to_calc, entered_weight if price_to_calc > 10000 else 1)) / 0.545

                p_profit_class = "profit-positive" if p_profit >= 0 else "profit-negative"
                profit_per_stock = round(p_profit * int(quantity)) if quantity else 0

                st.markdown(f"""
                <div class="calc-result {p_profit_class}"><b>Прибыль:</b> {round(p_profit):,} ₸</div>
                <div class="calc-result"><b>Рентабельность:</b> {round(rent)} %</div>
                <div class="calc-result"><b>Маржа:</b> {round(margin)} %</div>
                <div class="calc-result"><b>Прибыль с остатка:</b> {profit_per_stock:,} ₸</div>
                <div class="rec-prices"><b>Цены к рассмотрению:</b> {round(rec_price1):,} ₸ и {round(rec_price2):,} ₸</div>
                """, unsafe_allow_html=True)

            with col3:
                if not daily_sales.empty:
                    has_price_col = 'Средняя_цена' in daily_sales.columns
                    fig = px.line(
                        daily_sales,
                        x='Дата поступления заказа',
                        y='Количество',
                        markers=True,
                        line_shape='spline',
                        height=200,
                        hover_data={'Средняя_цена': ':.0f'} if has_price_col else None,
                        labels={'Средняя_цена': 'Ср. цена, ₸'}
                    )
                    fig.update_traces(
                        line=dict(width=2.5, color='#2563eb'),
                        marker=dict(size=5, color='#2563eb')
                    )
                    fig.update_xaxes(
                        range=[x_axis_start, x_axis_end],
                        tickformat="%d.%m",
                        tickfont=dict(size=10),
                        showgrid=False
                    )
                    fig.update_yaxes(
                        rangemode='tozero',
                        tickfont=dict(size=10),
                        showgrid=True,
                        gridcolor='#f1f5f9'
                    )
                    fig.update_layout(
                        margin=dict(l=0, r=0, t=8, b=0),
                        showlegend=False,
                        plot_bgcolor='white',
                        paper_bgcolor='white'
                    )
                    st.plotly_chart(fig, use_container_width=True, key=f"chart_{article}")

            # _art_manual = st.session_state.get('gsheet_manual', {}).get(str(article), {})
            # _col_pm, _col_ms = st.columns(2)
            # with _col_pm:
            #     st.number_input("Продавать в месяц", value=float(_art_manual.get('prod_month', 0) or 0),
            #         min_value=0.0, step=1.0, format="%.0f", key=f"pm_{article}",
            #         on_change=_on_manual_change, args=(article, "prod_month", _COL_PROD_MONTH))
            # with _col_ms:
            #     st.number_input("Неснижаемый остаток", value=float(_art_manual.get('min_stock', 0) or 0),
            #         min_value=0.0, step=1.0, format="%.0f", key=f"ms_{article}",
            #         on_change=_on_manual_change, args=(article, "min_stock", _COL_MIN_STOCK))
            _art_manual = st.session_state.get('gsheet_manual', {}).get(str(article), {})
            st.text_input(
                "Комментарий",
                value=_art_manual.get('comment', '') or '',
                key=f"comment_{article}",
                on_change=_on_comment_change,
                args=(article,),
            )
            _save_err = st.session_state.get('_gsheet_save_error')
            if _save_err:
                st.warning(f"⚠️ Комментарий не сохранён: {_save_err}")

            st.markdown('<hr class="card-divider">', unsafe_allow_html=True)
          
            
        if show_all_mode:
            render_pagination_controls(current_page, total_pages, position="bottom")
else:
    st.info("👈 Пожалуйста, загрузите файлы CSV в меню слева, чтобы начать работу.")
