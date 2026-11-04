from streamlit.web import bootstrap

if __name__ == "__main__":
    bootstrap.run("src/dashboard/app.py", "", [], flag_options={
        "server.port": 8501,
        "server.headless": True,
        "browser.gatherUsageStats": False,
    })
