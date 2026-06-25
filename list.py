import streamlit as st
import pandas as pd
import plotly.express as px

st.set_page_config(page_title="Аналитика продаж", layout="wide")
st.title('Динамика продаж')

# --- ПАНЕЛЬ ЗАГРУЗКИ ФАЙЛОВ ---
st.sidebar.header("📁 Загрузка данных")
st.sidebar.write("Прикрепите выгрузки заказов (ArchiveOrders и ActiveOrders)")
uploaded_files = st.sidebar.file_uploader(
    "Выберите один или несколько CSV файлов", 
    type=['csv'], 
    accept_multiple_files=True
)

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

# --- ОСНОВНАЯ ЛОГИКА ---
if uploaded_files:
    df = process_uploaded_files(uploaded_files)
    
    if not df.empty:
        max_date = df['Дата поступления заказа'].max()
        thirty_days_ago = max_date - pd.Timedelta(days=30)
        
        global_min_date = df['Дата поступления заказа'].min()
        global_max_date = max_date
        x_axis_start = global_min_date - pd.Timedelta(days=1)
        x_axis_end = global_max_date + pd.Timedelta(days=1)
        
        st.markdown(f"🗓️ *Метрика за последние 30 дней: с **{thirty_days_ago.strftime('%d.%m.%Y')}** по **{max_date.strftime('%d.%m.%Y')}***")
        st.markdown("---")
        
        col_search, col_btn = st.columns([2, 1])
        with col_search:
            search_mode = st.radio("Искать товар по:", ["Артикулу", "Названию в системе продавца"], horizontal=True)
            if search_mode == "Артикулу":
                unique_options = sorted(df['Артикул'].unique())
                selected_val = st.selectbox("Выберите артикул:", options=unique_options)
            else:
                unique_options = sorted(df['Название в системе продавца'].unique())
                selected_val = st.selectbox("Выберите название:", options=unique_options)
                
        with col_btn:
            st.write("")
            st.write("")
            show_all = st.button("Показать продажи по всем карточкам", use_container_width=True)

        st.markdown("---")

        articles_to_show = []
        if show_all:
            articles_to_show = sorted(df['Артикул'].unique())
        elif selected_val:
            if search_mode == "Артикулу":
                articles_to_show = [selected_val]
            else:
                articles_to_show = sorted(df[df['Название в системе продавца'] == selected_val]['Артикул'].unique())

        for article in articles_to_show:
            product_df = df[df['Артикул'] == article]
            
            product_name = "Не указано"
            if 'Название в системе продавца' in product_df.columns:
                product_name = product_df['Название в системе продавца'].iloc[0]
            
            recent_sales_df = product_df[product_df['Дата поступления заказа'] >= thirty_days_ago]
            total_sold_30_days = int(recent_sales_df['Количество'].sum())
            
            daily_sales = product_df.groupby('Дата поступления заказа')['Количество'].sum().reset_index()
            daily_sales = daily_sales.sort_values('Дата поступления заказа')
            
            col1, col2 = st.columns([1, 2])
            with col1:
                st.markdown(f"### 📦 `{article}`")
                st.markdown(f"**{product_name}**")
                st.metric(label="Продано (30 дней)", value=f"{total_sold_30_days} шт.")
                
            with col2:
                if not daily_sales.empty:
                    fig = px.bar(
                        daily_sales, 
                        x='Дата поступления заказа', 
                        y='Количество',
                        height=220, 
                        text_auto=True
                    )
                    fig.update_xaxes(range=[x_axis_start, x_axis_end], tickformat="%d.%m.%Y")
                    fig.update_layout(margin=dict(l=10, r=10, t=10, b=10), showlegend=False)
                    st.plotly_chart(fig, use_container_width=True, key=f"chart_{article}")
            st.markdown("---")
else:
    st.info("👈 Пожалуйста, загрузите файлы CSV в меню слева, чтобы начать работу.")