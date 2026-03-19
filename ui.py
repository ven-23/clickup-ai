import streamlit as st
import requests
import json
import os

# Configuration
API_URL = os.getenv("API_URL", "http://localhost:8000")

st.set_page_config(page_title="ClickUp AI Agent", page_icon="📊", layout="wide")

# Custom CSS for Premium Look
st.markdown("""
<style>
    .stApp {
        background: linear-gradient(135deg, #0e1117 0%, #161b22 100%);
        color: #fafbfc;
    }
    [data-testid="stChatMessageContent"] {
        color: #fafbfc !important;
    }
    .stChatMessage {
        border-radius: 15px;
        background-color: rgba(255, 255, 255, 0.03);
        backdrop-filter: blur(12px);
        border: 1px solid rgba(255, 255, 255, 0.1);
        margin-bottom: 15px;
    }
    h1, h2, h3, p, span {
        color: #fafbfc !important;
    }
    .stButton>button {
        background: linear-gradient(90deg, #6a11cb 0%, #2575fc 100%);
        color: white !important;
        border: none;
        border-radius: 8px;
        font-weight: bold;
    }
    /* Expander styling */
    .streamlit-expanderHeader {
        background-color: rgba(255, 255, 255, 0.03) !important;
        border-radius: 8px !important;
    }
</style>
""", unsafe_allow_html=True)

st.title("🚀 ClickUp AI Analyst")
st.markdown("""
Explore your team's productivity with precision. Ask about ** July tracked time, billable ratios, or high-value users**.
""")

# Initialize chat history
if "messages" not in st.session_state:
    st.session_state.messages = []

# Display chat messages from history on app rerun
for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        st.markdown(message["content"])
        if message.get("results"):
            _, col, _ = st.columns([1, 8, 1])
            with col:
                st.dataframe(message["results"], use_container_width=True)

# React to user input
if prompt := st.chat_input("Analyze your data..."):
    st.chat_message("user").markdown(prompt)
    st.session_state.messages.append({"role": "user", "content": prompt})

    with st.chat_message("assistant"):
        message_placeholder = st.empty()
        message_placeholder.markdown("🔍 **Analyzing patterns...**")
        
        try:
            payload = {
                "message": prompt,
                "history": [{"role": m["role"], "content": m["content"]} for m in st.session_state.messages[:-1]]
            }
            response = requests.post(f"{API_URL}/chat", json=payload)
            
            if response.status_code == 200:
                data = response.json()
                ai_response = data["response"]
                query_results = data.get("query_results", [])
                
                # Redundancy Fix: Strip ASCII tables if the UI is showing a dynamic table
                if query_results and (" | " in ai_response or "---" in ai_response):
                    # Keep only the part before many consecutive dashes or bars
                    lines = ai_response.split('\n')
                    clean_lines = []
                    for line in lines:
                        if " | " in line or "---" in line or "RESULT" in line:
                            break
                        clean_lines.append(line)
                    ai_response = "\n".join(clean_lines).strip()
                
                message_placeholder.markdown(ai_response)
                
                # Center the dynamic table
                if query_results:
                    _, col, _ = st.columns([1, 8, 1])
                    with col:
                        st.dataframe(query_results, use_container_width=True)
                
                st.session_state.messages.append({
                    "role": "assistant", 
                    "content": ai_response,
                    "results": query_results
                })
            else:
                message_placeholder.error(f"Error {response.status_code}: {response.text}")
        except Exception as e:
            message_placeholder.error(f"Pipeline error: {str(e)}")

# Sidebar with stats or info
with st.sidebar:
    st.header("Project Info")
    st.info("""
    **Version**: 4.0 (Architectural Overhaul)
    **Core**: LangGraph + MCP
    **Backend**: FastAPI
    **Frontend**: Streamlit
    """)
    if st.button("Clear History"):
        st.session_state.messages = []
        st.rerun()
