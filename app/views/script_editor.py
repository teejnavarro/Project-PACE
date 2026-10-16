# app/views/script_editor.py
"""Developer-only Script Editor view."""

from pathlib import Path

import streamlit as st

from storage import channel_dir
from ui import (
    ROOT, _SCRIPT_EDITOR_FILES, _is_developer,
)


def _script_editor_path(rel_path: str) -> Path:
    if rel_path.startswith("reference_data/"):
        return ROOT / rel_path
    return channel_dir("") / rel_path


def render_script_editor():
    """Developer-only in-app editor for core SQL/Jinja2 template files."""
    if not _is_developer():
        st.warning("Script Editor is available for Developers only.")
        if st.button("← Back to Dashboard", key="scripts_back_nodev"):
            st.session_state.view = "dashboard"
            st.rerun()
        return

    st.header("📝 Script Editor")
    st.caption("Edit the core SQL and Jinja2 template files that power campaign generation.")

    col_back, _col_spacer = st.columns([1, 5])
    with col_back:
        if st.button("← Dashboard", key="scripts_back_btn"):
            st.session_state.view = "dashboard"
            st.rerun()

    # ---- File selector ----
    labels = [k for k, v in _SCRIPT_EDITOR_FILES.items() if _script_editor_path(v).exists()]
    selected_label = st.selectbox(
        "Select script to edit",
        labels,
        key="script_editor_select",
    )
    rel_path = _SCRIPT_EDITOR_FILES[selected_label]
    file_path = _script_editor_path(rel_path)

    if not file_path.exists():
        st.error(f"File not found: `{rel_path}`")
        return

    # ---- Load content (or use session-state draft) ----
    state_key = f"_script_draft_{file_path}"
    disk_key = f"_script_disk_{file_path}"

    # Read disk version
    disk_content = file_path.read_text(encoding="utf-8")

    # First load or file changed on disk since last read
    if state_key not in st.session_state or st.session_state.get(disk_key) != disk_content:
        st.session_state[state_key] = disk_content
        st.session_state[disk_key] = disk_content

    # ---- Editor area ----
    edited = st.text_area(
        f"Editing: `{rel_path}`",
        value=st.session_state[state_key],
        height=500,
        key=f"_script_ta_{file_path}",
    )

    # Track draft changes
    st.session_state[state_key] = edited

    has_changes = edited != st.session_state[disk_key]

    # ---- Action buttons ----
    bcol1, bcol2, bcol3 = st.columns([1, 1, 4])
    with bcol1:
        save_disabled = not has_changes
        if st.button("💾 Save", key="script_save_btn", type="primary", disabled=save_disabled, use_container_width=True):
            file_path.write_text(edited, encoding="utf-8")
            st.session_state[disk_key] = edited
            st.success(f"Saved `{rel_path}`")
            st.rerun()
    with bcol2:
        if st.button("↩️ Revert", key="script_revert_btn", disabled=not has_changes, use_container_width=True):
            st.session_state[state_key] = st.session_state[disk_key]
            st.rerun()

    if has_changes:
        st.info("You have unsaved changes.")

    # ---- Diff preview ----
    if has_changes:
        with st.expander("📄 Show diff", expanded=False):
            import difflib
            diff_lines = difflib.unified_diff(
                st.session_state[disk_key].splitlines(keepends=True),
                edited.splitlines(keepends=True),
                fromfile=f"{rel_path} (on disk)",
                tofile=f"{rel_path} (edited)",
                lineterm="",
            )
            diff_text = "\n".join(diff_lines)
            if diff_text.strip():
                st.code(diff_text, language="diff")
            else:
                st.write("No differences.")
