FROM python:3.13-slim

WORKDIR /app

COPY requirements-app.txt .
RUN pip install --no-cache-dir -r requirements-app.txt

COPY app.py .
COPY app_data/ app_data/

ENV STREAMLIT_SERVER_HEADLESS=true \
    STREAMLIT_BROWSER_GATHER_USAGE_STATS=false

EXPOSE 8000
CMD ["streamlit", "run", "app.py", "--server.port=8000", "--server.address=0.0.0.0"]
