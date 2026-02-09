# utils/auth.py
import streamlit as st

# -------------------------
# Config: roles & permissions
# -------------------------
DEFAULT_ROLE = "viewer"

def _get_users_map() -> dict:
    # secrets: [users]
    return dict(st.secrets.get("users", {}))

def _get_permissions() -> dict:
    # secrets: [permissions]
    return dict(st.secrets.get("permissions", {}))

def get_role(username: str) -> str:
    users = _get_users_map()
    return users.get(username, DEFAULT_ROLE)

def can_export_excel() -> bool:
    username = st.session_state.get("username", "")
    role = st.session_state.get("role", DEFAULT_ROLE)

    perms = _get_permissions()
    export_users = perms.get("export_excel_users", [])

    # admin always allowed
    return (role == "admin") or (username in export_users)

def can_save_to_gsheets() -> bool:
    # contoh: editor & admin boleh simpan
    role = st.session_state.get("role", DEFAULT_ROLE)
    return role in ("editor", "admin")

def can_upload_source() -> bool:
    # contoh: admin saja
    role = st.session_state.get("role", DEFAULT_ROLE)
    return role == "admin"


# -------------------------
# Login UI (username-only)
# -------------------------
def require_login(page_title: str = "🔐 Login") -> None:
    """Block app execution until user logs in with a known username."""
    if st.session_state.get("auth_ok"):
        return

    st.title(page_title)
    st.caption("Masukkan username untuk mengakses aplikasi.")

    allowed = _get_users_map()

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

    # stop app rendering before login
    st.stop()

def render_user_badge(where: str = "sidebar") -> None:
    """Show current logged user + logout button."""
    username = st.session_state.get("username", "-")
    role = st.session_state.get("role", DEFAULT_ROLE)

    if where == "sidebar":
        st.sidebar.markdown("---")
        st.sidebar.write(f"Login: **{username}**  \nRole: **{role}**")
        if st.sidebar.button("🚪 Logout", use_container_width=True):
            logout()
    else:
        cols = st.columns([4, 1])
        cols[0].write(f"Login: **{username}** | Role: **{role}**")
        if cols[1].button("🚪 Logout"):
            logout()

def logout() -> None:
    """Clear session and go back to login page."""
    for k in ["auth_ok", "username", "role", "excel_bytes"]:
        st.session_state.pop(k, None)
    st.rerun()
