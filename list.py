import streamlit as st
import pandas as pd
import plotly.express as px

# Настройка страницы Streamlit: заголовок и широкий макет для удобного отображения аналитики.
st.set_page_config(page_title="Аналитика продаж", layout="wide")
# Основной заголовок приложения.
st.title('Динамика продаж')

# --- ПАНЕЛЬ ЗАГРУЗКИ ФАЙЛОВ ---
# Боковая панель для загрузки исходных CSV-файлов пользователем.
st.sidebar.header("📁 Загрузка данных")
st.sidebar.write("Прикрепите выгрузки заказов (ArchiveOrders и ActiveOrders)")

# Поле выбора одного или нескольких CSV-файлов с данными о продажах.
uploaded_files = st.sidebar.file_uploader(
    "Выберите один или несколько CSV файлов", 
    type=['csv'], 
    accept_multiple_files=True
)
# Поле выбора файла с остатками товара.
stock_file = st.sidebar.file_uploader("Остатки (CSV)", type=['csv'])
# Поле выбора файла со ссылками на карточки товаров.
links_file = st.sidebar.file_uploader("Ссылки", type=['csv'])

# Кэширование функции чтения и подготовки данных для ускорения повторных загрузок.
@st.cache_data
def process_uploaded_files(files):
    # Список датафреймов, загруженных из всех выбранных файлов.
    dfs = []
    for file in files:
        try:
            # Чтение CSV-файла в DataFrame.
            df = pd.read_csv(file)
            dfs.append(df)
        except Exception as e:
            # Вывод ошибки, если один из файлов не удалось прочитать.
            st.error(f"Ошибка при чтении файла {file.name}: {e}")
            return pd.DataFrame()
            
    if not dfs:
        # Если файлов нет или они не были прочитаны — возвращаем пустую таблицу.
        return pd.DataFrame()

    # Объединение всех выгрузок в одну таблицу.
    df = pd.concat(dfs, ignore_index=True)
    
    # Очищаем названия колонок от лишних пробелов.
    df.columns = df.columns.str.strip()
    # Нормализуем артикул: приводим к строке и убираем пробелы.
    df['Артикул'] = df['Артикул'].astype(str).str.strip()
    
    # Если в данных есть названия товаров, нормализуем их и заполняем пустые значения.
    if 'Название в системе продавца' in df.columns:
        df['Название в системе продавца'] = df['Название в системе продавца'].fillna('Не указано').astype(str).str.strip()
    
    # Преобразуем дату поступления заказа в datetime и количество в числовой формат.
    df['Дата поступления заказа'] = pd.to_datetime(df['Дата поступления заказа'], format='%d.%m.%Y', errors='coerce')
    df['Количество'] = pd.to_numeric(df['Количество'], errors='coerce').fillna(0)
    
    # Удаляем строки без даты или артикула, так как они не пригодны для анализа.
    df = df.dropna(subset=['Дата поступления заказа', 'Артикул'])
    return df

# Кэширование обработки файла с остатками для ускорения повторных запусков.
@st.cache_data
def process_stock(file):
    try:
        # Возвращаем указатель файла в начало, чтобы корректно прочитать его повторно.
        file.seek(0)
        # Читаем файл с остатками как сырой CSV, так как структура может быть нестандартной.
        raw_df = pd.read_csv(file, header=None, encoding='utf-8-sig', sep=None, engine='python')
        # Ищем строку, содержащую слово "Наименование" — это заголовок таблицы.
        mask = raw_df.apply(lambda row: row.astype(str).str.contains('Наименование', case=False, na=False).any(), axis=1)
        
        if not mask.any():
            # Если заголовок не найден, возвращаем None.
            return None
        
        # Находим индекс строки с заголовком и берём данные ниже неё.
        header_idx = mask.idxmax()
        df_stock = raw_df.iloc[header_idx+1:].copy()
        df_stock.columns = raw_df.iloc[header_idx]
        df_stock.columns = df_stock.columns.str.strip()
        # Удаляем пустые строки, где нет названия товара.
        df_stock = df_stock.dropna(subset=['Наименование'])
        # Добавляем нормализованное название для сопоставления с товарами из заказов.
        df_stock['Наименование_clean'] = df_stock['Наименование'].astype(str).str.strip().str.lower()
        
        # Преобразуем числовые колонки в числовой формат, заменяя запятые на точки.
        for col in ['Остаток', 'Резерв', 'Себестоимость']:
            if col in df_stock.columns:
                df_stock[col] = pd.to_numeric(df_stock[col].astype(str).str.replace(',', '.'), errors='coerce').fillna(0)
        return df_stock
    except:
        # В случае любой ошибки при обработке файла с остатками — возвращаем None.
        return None

# Кэширование обработки CSV-файла со ссылками на карточки товаров.
@st.cache_data
def process_links(file):
    try:
        # Возвращаем курсор файла в начало, чтобы прочитать его снова.
        file.seek(0)
        # Читаем файл со ссылками в DataFrame.
        df = pd.read_csv(file, encoding='utf-8-sig')
        df.columns = df.columns.str.strip()

        # Если в файле есть нужные колонки — берём их напрямую.
        if 'Артикул' in df.columns and 'Ссылка' in df.columns:
            links_df = df[['Артикул', 'Ссылка']].copy()
        # Иначе пробуем взять первый столбец как артикул и четвёртый как ссылку.
        elif len(df.columns) >= 4:
            links_df = pd.DataFrame({
                'Артикул': df.iloc[:, 0].astype(str).str.strip(),
                'Ссылка': df.iloc[:, 3].astype(str).str.strip()
            })
        else:
            # Если структура файла не совпадает — возвращаем пустую таблицу.
            return pd.DataFrame(columns=['Артикул', 'Ссылка'])

        # Нормализуем данные: убираем пробелы и пустые строки.
        links_df['Артикул'] = links_df['Артикул'].astype(str).str.strip()
        links_df['Ссылка'] = links_df['Ссылка'].astype(str).str.strip()
        links_df = links_df[links_df['Артикул'] != '']
        links_df = links_df[links_df['Ссылка'] != '']
        # Удаляем дубли по артикулу, чтобы не было конфликтов.
        return links_df.drop_duplicates(subset=['Артикул'])
    except Exception:
        # В случае ошибки возвращаем пустую таблицу.
        return pd.DataFrame(columns=['Артикул', 'Ссылка'])


# Функция для отображения навигации по страницам в режиме просмотра всех карточек.
def render_pagination_controls(current_page, total_pages, position="middle"):
    # Создаём четыре колонки: назад, информация о странице, ввод номера страницы, вперёд.
    col_prev, col_page, col_input, col_next = st.columns([1, 1, 2, 1])
    with col_prev:
        # Кнопка перехода на предыдущую страницу.
        if st.button("← Назад", key=f"prev_page_{position}_{current_page}", use_container_width=True, disabled=current_page == 1):
            st.session_state.all_articles_page = current_page - 1
    with col_page:
        # Отображаем текущую страницу и общее число страниц.
        st.markdown(f"<div style='text-align:center;'><b>Страница {current_page} из {total_pages}</b></div>", unsafe_allow_html=True)
    with col_input:
        # Поле ввода для быстрого перехода на нужную страницу.
        new_page = st.number_input(
            "Номер страницы",
            min_value=1,
            max_value=total_pages,
            value=current_page,
            step=1,
            label_visibility="collapsed",
            key=f"page_number_input_{position}_{current_page}"
        )
        if new_page != current_page:
            # При изменении номера страницы обновляем состояние и выполняем переход.
            st.session_state.all_articles_page = int(new_page)
    with col_next:
        # Кнопка перехода на следующую страницу.
        if st.button("Вперёд →", key=f"next_page_{position}_{current_page}", use_container_width=True, disabled=current_page == total_pages):
            st.session_state.all_articles_page = current_page + 1


# --- ОСНОВНАЯ ЛОГИКА ---
# Основной блок приложения: выполняется только если пользователь загрузил хотя бы один CSV-файл.
if uploaded_files:
    # Подготовка основных данных: продажи, остатки и ссылки.
    df = process_uploaded_files(uploaded_files)
    stock_df = process_stock(stock_file) if stock_file else None
    links_df = process_links(links_file) if links_file else None
    
    # Если после обработки данных получена не пустая таблица — строим интерфейс аналитики.
    if not df.empty:
        # Определяем диапазон дат для отображения и оси графика.
        max_date = df['Дата поступления заказа'].max()
        thirty_days_ago = max_date - pd.Timedelta(days=30)
        
        global_min_date = df['Дата поступления заказа'].min()
        global_max_date = max_date
        x_axis_start = global_min_date - pd.Timedelta(days=1)
        x_axis_end = global_max_date + pd.Timedelta(days=1)
        
        # Выводим метку с диапазоном последних 30 дней.
        st.markdown(f"🗓️ *Метрика за последние 30 дней: с **{thirty_days_ago.strftime('%d.%m.%Y')}** по **{max_date.strftime('%d.%m.%Y')}***")
        st.markdown("---")
        
        # Разделяем интерфейс на две колонки: поиск товара и кнопка показа всех карточек.
        col_search, col_btn = st.columns([2, 1])
        with col_search:
            # Выбор режима поиска: по артикулу или по названию.
            search_mode = st.radio("Искать товар по:", ["Артикулу", "Названию в системе продавца"], horizontal=True)
            if search_mode == "Артикулу":
                # Список уникальных артикулов для выбора.
                unique_options = sorted(df['Артикул'].unique())
                selected_val = st.selectbox("Выберите артикул:", options=unique_options)
            else:
                # Список уникальных названий для выбора.
                unique_options = sorted(df['Название в системе продавца'].unique())
                selected_val = st.selectbox("Выберите название:", options=unique_options)
                
        with col_btn:
            # Добавляем пустое пространство для визуального выравнивания кнопки.
            st.write("")
            st.write("")
            # Кнопка включения режима показа всех карточек с постраничной навигацией.
            if st.button("Показать продажи по всем карточкам", use_container_width=True):
                st.session_state.show_all_mode = True
                st.session_state.all_articles_page = 1

        st.markdown("---")

        # Определяем, активен ли режим показа всех карточек, а также параметры пагинации.
        show_all_mode = st.session_state.get("show_all_mode", False)
        page_size = 15
        current_page = st.session_state.get("all_articles_page", 1)
        total_pages = 1

        articles_to_show = []
        if show_all_mode:
            # Формируем список всех уникальных артикулов, отсортированный по названию продавца.
            product_lookup = df[['Артикул', 'Название в системе продавца']].drop_duplicates(subset=['Артикул']).copy()
            product_lookup['Название в системе продавца'] = product_lookup['Название в системе продавца'].fillna('Не указано').astype(str).str.strip()
            product_lookup['sort_name'] = product_lookup['Название в системе продавца'].str.lower()
            all_articles = product_lookup.sort_values(['sort_name', 'Артикул'])['Артикул'].tolist()

            # Подсчитываем количество страниц для пагинации.
            total_pages = max(1, (len(all_articles) + page_size - 1) // page_size)
            current_page = max(1, min(current_page, total_pages))
            st.session_state.all_articles_page = current_page

            # Определяем диапазон артикулов для текущей страницы.
            start_idx = (current_page - 1) * page_size
            end_idx = start_idx + page_size
            articles_to_show = all_articles[start_idx:end_idx]

            # Отображаем навигацию по страницам в начале списка.
            render_pagination_controls(current_page, total_pages, position="top")
            st.markdown("---")
        elif selected_val:
            # Если режим показа всех карточек не активен, показываем только выбранный товар.
            if search_mode == "Артикулу":
                articles_to_show = [selected_val]
            else:
                articles_to_show = sorted(df[df['Название в системе продавца'] == selected_val]['Артикул'].unique())

        # Проходим по каждому артикулу и строим карточку товара.
        for article in articles_to_show:
            # Выделяем из общей таблицы только строки, относящиеся к текущему артикулу.
            product_df = df[df['Артикул'] == article]
            # Берём название товара из строки данных для последующего сопоставления с остатками.
            prod_name = product_df['Название в системе продавца'].iloc[0]
            prod_name_clean = str(prod_name).strip().lower()

            stock_info = "Это комплект"
            cost_info = "Н/Д"
            if stock_df is not None:
                match = stock_df[stock_df['Наименование_clean'] == prod_name_clean]
                if not match.empty:
                    row = match.iloc[0]
                    qty = row['Остаток'] - row['Резерв']
                    stock_info = f"{int(qty)} шт."
                    cost_info = f"{row['Себестоимость']:,.2f} ₸"
                    cost = row['Себестоимость']
            else:
                stock_info = "0"
            
            product_name = "Не указано"
            if 'Название в системе продавца' in product_df.columns:
                product_name = product_df['Название в системе продавца'].iloc[0]

            link_url = None
            if links_df is not None and not links_df.empty:
                match = links_df[links_df['Артикул'] == article]
                if not match.empty:
                    link_url = match.iloc[0]['Ссылка']
            
            # Считаем продажи и выручку за последние 30 дней для текущего товара.
            recent_sales_df = product_df[product_df['Дата поступления заказа'] >= thirty_days_ago]
            total_sold_30_days = int(recent_sales_df['Количество'].sum())
            totalrevenue = int(recent_sales_df['Сумма'].sum())
           
            # Рассчитываем прибыль, если для товара доступна себестоимость.
            if not cost_info == "Н/Д":
                 profit = totalrevenue*0.845 - cost*total_sold_30_days
            else:
                 profit = 0 
            
            # Группируем продажи по датам, чтобы отрисовать плавный график.
            daily_sales = product_df.groupby('Дата поступления заказа')['Количество'].sum().reset_index()
            daily_sales = daily_sales.sort_values('Дата поступления заказа')
            
            # Разбиваем карточку товара на три зоны: информация, метрики и график.
            col1, col2, col3 = st.columns([1, 1,2])
            with col1:
                if link_url:
                    st.markdown(f"### 📦 [{article}]({link_url})")
                else:
                    st.markdown(f"### 📦 {article}")
                st.markdown(f"**{product_name}**")
                st.metric(label="Продано (30 дней)", value=f"{total_sold_30_days} шт.")
            with col2:
                st.metric("Себестоимость", cost_info)    
                st.metric("Остаток", stock_info)
                st.metric("Прибыль", value=f"{round(profit)} ₸.")
               
            with col3:
                if not daily_sales.empty:
                    fig = px.line(
                        daily_sales,
                        x='Дата поступления заказа',
                        y='Количество',
                        markers=True,
                        line_shape='spline',
                        height=220
                    )
                    fig.update_traces(line=dict(width=3), marker=dict(size=6))
                    fig.update_xaxes(range=[x_axis_start, x_axis_end], tickformat="%d.%m.%Y")
                    fig.update_layout(margin=dict(l=10, r=10, t=10, b=10), showlegend=False)
                    st.plotly_chart(fig, use_container_width=True, key=f"chart_{article}")
            
            st.markdown("---")
        if show_all_mode:
            render_pagination_controls(current_page, total_pages, position="bottom")
else:
    st.info("👈 Пожалуйста, загрузите файлы CSV в меню слева, чтобы начать работу.")
