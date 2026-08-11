import streamlit as st

# 1. Initialize safe persistent state variables
if "response_text" not in st.session_state:
    st.session_state.response_text = ""

# 2. Extract execution out of the structural 'if button' check
def execute_agent_action():
    user_query = st.session_state.user_command
    if user_query:
        # INSERT YOUR ACTUAL AGENT/NETWORK INFERENCE CALL HERE
        # e.g., response = run_ai_agent(user_query)
        st.session_state.response_text = f"Processed query: '{user_query}'."
    else:
        st.session_state.response_text = "Please type a plain text command."

st.title("Mobile AI Multitask Agent")
st.caption("Type commands in plain text. Your interface handles processing automatically!")

# 3. Use 'key' to store inputs directly into the session_state engine
st.text_input("Your Command", key="user_command")

# 4. Trigger the exact callback execution explicitly on click 1
st.button("Execute Action", on_click=execute_agent_action, type="primary")

# 5. Render output out of a persistent memory box
if st.session_state.response_text:
    st.write("### AI System Response")
    st.info(st.session_state.response_text)
