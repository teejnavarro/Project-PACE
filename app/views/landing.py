# app/views/landing.py
"""Channel landing page and sidebar channel selector."""

import streamlit as st

from storage import set_active_channel
from ui import _CHANNEL_TAGLINES


def _render_channel_selector():
    """Sidebar PUSH ↔ RCS toggle + back-to-landing button."""
    st.markdown("<div style='font-size:0.72em;color:var(--pace-text-muted);font-weight:600;letter-spacing:0.08em;text-transform:uppercase;margin-bottom:6px;'>Channel</div>", unsafe_allow_html=True)
    _current_channel = st.session_state.get("channel", "push") or "push"
    chan_col1, chan_col2 = st.columns(2)
    with chan_col1:
        if st.button("📱 PUSH", key="channel_push_btn", type="primary" if _current_channel == "push" else "secondary", use_container_width=True):
            if _current_channel != "push":
                st.session_state.channel = "push"
                set_active_channel("push")
                st.session_state.active_campaign_id = None
                st.session_state.view = "dashboard"
                st.rerun()
    with chan_col2:
        if st.button("💬 RCS", key="channel_rcs_btn", type="primary" if _current_channel == "rcs" else "secondary", use_container_width=True):
            if _current_channel != "rcs":
                st.session_state.channel = "rcs"
                set_active_channel("rcs")
                st.session_state.active_campaign_id = None
                st.session_state.view = "dashboard"
                st.rerun()
    if st.button("← Back to landing", key="back_to_landing_btn", use_container_width=True):
        st.session_state.channel = None
        st.session_state.active_campaign_id = None
        st.session_state.view = "landing"
        st.rerun()
    st.divider()


def render_landing():
    """Channel selection landing page. Shown when st.session_state.channel is None."""
    st.markdown("""
    <div style="text-align:center;padding:60px 0 20px 0;">
        <div style="display:inline-block;padding:18px 44px;border-radius:22px;
                    background:linear-gradient(135deg, rgba(87,155,252,0.18) 0%, rgba(162,93,220,0.12) 100%);
                    border:1px solid rgba(87,155,252,0.30);
                    box-shadow:0 8px 32px rgba(87,155,252,0.20);">
            <div style="font-size:5em;font-weight:800;letter-spacing:0.18em;line-height:1;
                        background:linear-gradient(135deg, #6ba9ff 0%, #a25ddc 100%);
                        -webkit-background-clip:text;-webkit-text-fill-color:transparent;
                        background-clip:text;">P·A·C·E</div>
        </div>
        <div style="font-size:1em;color:var(--pace-text-muted);margin-top:18px;letter-spacing:0.14em;
                    font-weight:600;text-transform:uppercase;">
            PROJECT · AUDIENCE · CAMPAIGN · EDITOR
        </div>
        <div style="font-size:1.1em;color:var(--pace-text-muted);margin-top:36px;">
            Which channel are you building today?
        </div>
    </div>
    """, unsafe_allow_html=True)

    st.markdown("<div style='height:24px;'></div>", unsafe_allow_html=True)

    _sp1, c1, _mid, c2, _sp2 = st.columns([1, 2, 0.4, 2, 1], vertical_alignment="top")
    # Fixed vertical rhythm so both cards line up regardless of tagline wrap:
    #   title block: 3.2em line + fixed padding
    #   tagline block: reserves 3 lines of copy (min-height:3.9em)
    _card_title_style = (
        "font-size:2.6em;font-weight:800;letter-spacing:0.10em;"
        "line-height:1.15;height:1.15em;display:flex;align-items:center;justify-content:center;"
    )
    _card_tagline_style = (
        "font-size:0.9em;color:var(--pace-text-muted);margin-top:12px;"
        "min-height:3.9em;line-height:1.3;display:flex;align-items:flex-start;"
        "justify-content:center;text-align:center;"
    )
    with c1:
        st.markdown(f"""
        <div style="text-align:center;padding:20px 0 8px 0;">
            <div style="{_card_title_style}color:var(--pace-primary);">📱 PUSH</div>
            <div style="{_card_tagline_style}">
                <span>{_CHANNEL_TAGLINES['push']}</span>
            </div>
        </div>
        """, unsafe_allow_html=True)
        if st.button("Enter PUSH", key="landing_push_btn", type="primary", use_container_width=True):
            st.session_state.channel = "push"
            set_active_channel("push")
            st.session_state.view = "dashboard"
            st.rerun()
    with c2:
        st.markdown(f"""
        <div style="text-align:center;padding:20px 0 8px 0;">
            <div style="{_card_title_style}color:var(--pace-purple);">💬 RCS</div>
            <div style="{_card_tagline_style}">
                <span>{_CHANNEL_TAGLINES['rcs']}</span>
            </div>
        </div>
        """, unsafe_allow_html=True)
        if st.button("Enter RCS", key="landing_rcs_btn", type="primary", use_container_width=True):
            st.session_state.channel = "rcs"
            set_active_channel("rcs")
            st.session_state.view = "dashboard"
            st.rerun()
