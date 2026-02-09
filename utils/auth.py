import streamlit as st

DEFAULT_ROLE = "viewer"

def _users_map() -> dict:
    # secrets.toml: [users]
    return dict(st.secrets.get("users", {}))

def _permissions() -> dict:
    # secrets.toml: [permissions]
    return dict(st.secrets.get("permissions", {}))

def require_login(page_title: str = "🔐 Login") -> None:
    """Block app execution until user logs in (username-only, no password)."""
    if st.session_state.get("auth_ok"):
        return

    st.title(page_title)
    st.caption("Masukkan username untuk mengakses aplikasi.")

    allowed = _users_map()

    with st.form("login_form", clear_on_submit=False):
        username = st.text_input("Username").strip()
        submitted = st.form_submit_button("Masuk")

    if submitted:
        if not username:
            st.error("Username wajib diisi.")
            st.stop()

        role = allowed.get(username)
        if not role:
            st.error("Username tidak terdaftar.")
            st.stop()

        st.session_state["auth_ok"] = True
        st.session_state["username"] = username
        st.session_state["role"] = role
        st.rerun()

    st.stop()

def logout() -> None:
    for k in ["auth_ok", "username", "role", "excel_bytes"]:
        st.session_state.pop(k, None)
    st.rerun()

def render_user_badge(where: str = "sidebar") -> None:
    username = st.session_state.get("username", "-")
    role = st.session_state.get("role", DEFAULT_ROLE)

    if where == "sidebar":
        st.sidebar.markdown("---")
        st.sidebar.write(f"Login: **{username}**  \nRole: **{role}**")
        if st.sidebar.button("🚪 Logout", use_container_width=True):
            logout()
    else:
        cols = st.columns([5, 1])
        cols[0].write(f"Login: **{username}** | Role: **{role}**")
        if cols[1].button("🚪 Logout"):
            logout()

def can_upload_source() -> bool:
    # Admin only
    return st.session_state.get("role", DEFAULT_ROLE) == "admin"

def can_save_to_gsheets() -> bool:
    # Admin only (adep)
    return st.session_state.get("role", DEFAULT_ROLE) == "admin"

def can_export_excel() -> bool:
    # Admin OR explicitly allowed users
    role = st.session_state.get("role", DEFAULT_ROLE)
    if role == "admin":
        return True
    username = st.session_state.get("username", "")
    export_users = _permissions().get("export_excel_users", [])
    return username in export_users
