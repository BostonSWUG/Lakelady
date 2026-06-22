"""
Lakelady - Streamlit UI

Web interface for the Lakelady Agile PLM file upload automation tool.
"""

import streamlit as st
import os
import time
import subprocess
import signal

# --- Page Config ---
st.set_page_config(
    page_title="Lakelady",
    page_icon="\U0001F9DC\u200D\u2640\uFE0F",
    layout="wide",
)

st.title("\U0001F9DC\u200D\u2640\uFE0F Lakelady")
st.markdown("Automated file uploads & downloads for Agile PLM Change Orders.")

# Reduce spacing around headings and dividers
st.markdown("""
<style>
    /* Reduce top padding from main content area */
    .main .block-container {
        padding-top: .5rem;
    }
    /* Shrink the Streamlit top toolbar without hiding it */
    header[data-testid="stHeader"] {
        height: 2rem !important;
        min-height: 2rem !important;
    }
    /* Reduce margin above the title */
    .main h1 {
        margin-top: 0 !important;
        padding-top: 0 !important;
    }
    /* Reduce top padding on main app container */
    .st-emotion-cache-zy6yx3 {
        padding-top: 2rem !important;
    }
    /* Reduce space above sidebar subheaders */
    [data-testid="stSidebar"] .stSubheader {
        margin-top: -0.5rem;
        margin-bottom: -0.5rem;
    }
    /* Reduce space around dividers in sidebar */
    [data-testid="stSidebar"] hr {
        margin-top: 0.5rem;
        margin-bottom: 0.5rem;
    }
    /* Reduce space above main area subheaders */
    .main .stSubheader {
        margin-top: 0rem;
        margin-bottom: -0.5rem;
    }
    /* Indent sidebar content except headings */
    [data-testid="stSidebar"] .stTextInput,
    [data-testid="stSidebar"] .stTextArea,
    [data-testid="stSidebar"] .stCheckbox,
    [data-testid="stSidebar"] .stAlert,
    [data-testid="stSidebar"] .stCaption,
    [data-testid="stSidebar"] .stColumn,
    [data-testid="stSidebar"] .stMarkdown:not(:has(h1)):not(:has(h2)):not(:has(h3)) {
        padding-left: 0.75rem;
    }
</style>
""", unsafe_allow_html=True)


# --- Session State Initialization ---
if "log_messages" not in st.session_state:
    st.session_state.log_messages = []
if "upload_running" not in st.session_state:
    st.session_state.upload_running = False
if "process" not in st.session_state:
    st.session_state.process = None


def add_log(message: str):
    """Add a timestamped message to the session state log."""
    st.session_state.log_messages.append(f"[{time.strftime('%H:%M:%S')}] {message}")


def read_process_output():
    """Read all available output from the subprocess without blocking."""
    if st.session_state.process is None:
        return

    proc = st.session_state.process

    # Read available output line by line (non-blocking via readline on PIPE)
    while True:
        line = proc.stdout.readline()
        if line:
            stripped = line.strip()
            if stripped:
                add_log(stripped)
        else:
            break


# --- Sidebar: Configuration ---
with st.sidebar:
    st.header("\u2699\uFE0F Configuration")

    # Mode toggle - pill-shaped switch with emoji icons
    if "download_mode" not in st.session_state:
        st.session_state.download_mode = False

    col_l, col_r = st.columns(2)
    with col_l:
        if st.button(
            "\U0001F4E4 Upload",
            use_container_width=True,
            type="primary" if not st.session_state.download_mode else "secondary",
        ):
            st.session_state.download_mode = False
            st.rerun()
    with col_r:
        if st.button(
            "\U0001F4E5 Download",
            use_container_width=True,
            type="primary" if st.session_state.download_mode else "secondary",
        ):
            st.session_state.download_mode = True
            st.rerun()

    download_mode = st.session_state.download_mode

    st.divider()

    username = st.text_input(
        "AR Username",
        value="",
        help="Your Amazon Robotics username for Agile login.",
    )

    st.divider()
    st.subheader("\U0001F4CB Change Orders")
    co_input = st.text_area(
        "Enter ECO/DECO numbers (one per line)",
        placeholder="DECO-06583\nDECO-07053\nMCO-12345",
        height=150,
        help="Enter one Change Order number per line. Supports DECO, MCO, ECO prefixes.",
    )

    # Validation message for Change Orders
    _co_list = [co.strip() for co in co_input.strip().split("\n") if co.strip()]

    st.divider()
    st.subheader("\U0001F4C1 File Location")
    folder_path = st.text_input(
        "Download to:" if download_mode else "Upload from:",
        value=r"C:\Solidworks Exports",
        help="Upload mode: folder containing exported files (named with part number prefix). "
        "Download mode: destination folder where PDFs will be saved (subfolders created per CO).",
    )

    # Show folder contents preview if path exists
    if folder_path and os.path.exists(folder_path):
        if not download_mode:
            st.success("Folder exists")

        if download_mode:
            create_subfolders = st.checkbox(
                "Create subfolder(s)",
                value=True,
                help="If checked, creates a subfolder named after each ECO/DECO within the path above.",
            )
            include_subfolders = False
        else:
            create_subfolders = False
            include_subfolders = st.checkbox(
                "Include subfolders",
                value=False,
                help="If checked, files in subfolders will also be included for upload.",
            )

            # Count files based on subfolder setting
            if include_subfolders:
                file_count = 0
                dir_count = 0
                for root, dirs, files in os.walk(folder_path):
                    file_count += len(files)
                    dir_count += len(dirs)
                st.caption(f"{file_count} files across {dir_count} subfolders (recursive)")
            else:
                files_in_folder = os.listdir(folder_path)
                file_count = len([f for f in files_in_folder if os.path.isfile(os.path.join(folder_path, f))])
                st.caption(f"{file_count} files (top-level only)")
    elif folder_path:
        if download_mode:
            # In download mode, folders will be created automatically
            create_subfolders = st.checkbox(
                "Create subfolder(s)",
                value=True,
                help="If checked, creates a subfolder named after each ECO/DECO within the path above.",
            )
            include_subfolders = False
        else:
            st.error("Folder not found")
            include_subfolders = False
            create_subfolders = False
    else:
        include_subfolders = False
        create_subfolders = False

    st.divider()
    st.subheader("\u2699\uFE0F Options")

    if download_mode:
        st.markdown("**File types to download:**")
        dl_pdf = st.checkbox("PDF", value=True, key="dl_pdf")
        dl_png = st.checkbox("PNG", value=False, key="dl_png")
        dl_xt = st.checkbox("x_t (Parasolid)", value=False, key="dl_xt")

        # Build filter string
        selected_types = []
        if dl_pdf:
            selected_types.append("pdf")
        if dl_png:
            selected_types.append("png")
        if dl_xt:
            selected_types.append("x_t")

        if not selected_types:
            file_filter = "all"
        elif len(selected_types) == 3:
            file_filter = "all"
        else:
            file_filter = ",".join(selected_types)
    else:
        file_filter = "pdf"

    if not download_mode:
        remove_existing = st.checkbox(
            "Remove existing attachments",
            value=True,
            help="If checked, existing attachments with matching file types will be "
            "removed before uploading new ones.",
        )
    else:
        remove_existing = False

    st.divider()
    st.markdown("**Lakelady**")
    st.caption(
        "Automates uploading SolidWorks export files to (or downloading PDF attachments from) "
        "Affected Items in Agile Change Orders."
    )
    st.caption("v2.1.0")


# --- Parse Change Orders ---
change_orders = [
    co.strip()
    for co in co_input.strip().split("\n")
    if co.strip()
]

# --- Validation & Preview ---
if change_orders and folder_path:
    if download_mode:
        st.subheader("\U0001F50D Pre-Download Preview")

        import pandas as pd

        preview_rows = []
        for co in change_orders:
            if create_subfolders:
                dl_path = os.path.join(folder_path, co)
            else:
                dl_path = folder_path

            # Count existing files in the target folder
            if os.path.exists(dl_path):
                existing_files = len([
                    f for f in os.listdir(dl_path)
                    if os.path.isfile(os.path.join(dl_path, f))
                ])
            else:
                existing_files = 0

            preview_rows.append({
                "Change Order": co,
                "Folder": dl_path,
                "Files": existing_files,
                "Overwrite": False,
            })

        preview_df = pd.DataFrame(preview_rows)
        edited_df = st.data_editor(
            preview_df,
            column_config={
                "Change Order": st.column_config.TextColumn(disabled=True),
                "Folder": st.column_config.TextColumn(disabled=True),
                "Files": st.column_config.NumberColumn(disabled=True, help="Files currently in folder"),
                "Overwrite": st.column_config.CheckboxColumn(
                    help="Check to overwrite existing files. Unchecked appends (1), (2), etc.",
                    default=False,
                ),
            },
            hide_index=True,
            use_container_width=True,
            disabled=["Change Order", "Folder", "Files"],
        )

        # Store overwrite settings per CO
        overwrite_map = {}
        for _, row in edited_df.iterrows():
            overwrite_map[row["Change Order"]] = row["Overwrite"]

    else:
        st.subheader("\U0001F50D Pre-Upload Preview")

        ignore_extensions = {"json", "log"}
        preview_data = []
        for co in change_orders:
            co_path = os.path.join(folder_path, co)
            if os.path.exists(co_path):
                file_count = len([
                    f for f in os.listdir(co_path)
                    if os.path.isfile(os.path.join(co_path, f))
                    and f.split(".")[-1].lower() not in ignore_extensions
                ])
                preview_data.append({
                    "Change Order": co,
                    "Folder": co_path,
                    "Files": file_count,
                    "Status": "\u2705 Ready",
                })
            else:
                if os.path.exists(folder_path):
                    root_files = [
                        f for f in os.listdir(folder_path)
                        if os.path.isfile(os.path.join(folder_path, f))
                        and f.split(".")[-1].lower() not in ignore_extensions
                    ]
                    preview_data.append({
                        "Change Order": co,
                        "Folder": folder_path + " (root)",
                        "Files": len(root_files),
                        "Status": "\u26A0\uFE0F No subfolder, using root",
                    })
                else:
                    preview_data.append({
                        "Change Order": co,
                        "Folder": "N/A",
                        "Files": 0,
                        "Status": "\u274C Path missing",
                    })

        st.dataframe(preview_data, use_container_width=True, hide_index=True)


# --- Upload Execution ---
col_btn1, col_btn2 = st.columns([1, 1])

with col_btn1:
    can_start = (
        bool(change_orders)
        and bool(folder_path)
        and (os.path.exists(folder_path) or download_mode)
        and bool(username)
        and not st.session_state.upload_running
    )

    start_upload = st.button(
        "\U0001F4E5 Start Download" if download_mode else "\U0001F680 Start Upload",
        disabled=not can_start,
        type="primary",
        use_container_width=True,
    )

with col_btn2:
    abort_upload = st.button(
        "\u26D4 Abort",
        disabled=not st.session_state.upload_running,
        type="secondary",
        use_container_width=True,
    )

if not username:
    st.warning("Enter your AR username in the sidebar.")
    if not change_orders:
        st.warning("Enter at least one Change Order number.")
elif not change_orders:
    st.warning("Enter at least one Change Order number.")
elif folder_path and not os.path.exists(folder_path) and not download_mode:
    st.error("File folder path does not exist.")
elif can_start:
    st.info("Ready to upload." if not download_mode else "Ready to download.")


# --- Handle Abort ---
if abort_upload and st.session_state.upload_running and st.session_state.process is not None:
    proc = st.session_state.process
    add_log("")
    add_log("\u26D4 ABORT requested - terminating process...")
    try:
        proc.terminate()
        proc.wait(timeout=5)
        add_log("Process terminated.")
    except Exception:
        try:
            proc.kill()
            add_log("Process killed (force).")
        except Exception as e:
            add_log(f"Failed to kill process: {e}")
    st.session_state.upload_running = False
    st.session_state.process = None
    st.rerun()


# --- Handle Upload Start ---
if start_upload:
    st.session_state.log_messages = []
    st.session_state.upload_running = True

    # Build the command
    remove_flag = "True" if remove_existing else "False"
    subfolders_flag = "True" if include_subfolders else "False"
    cmd_args = [username, remove_flag, folder_path, subfolders_flag] + change_orders

    # Add download mode flags if applicable
    if download_mode:
        cmd_args = ["--download", "--file-filter", file_filter]
        if create_subfolders:
            cmd_args.append("--create-subfolders")
        # Check if any CO has overwrite enabled
        if 'overwrite_map' in dir() and any(overwrite_map.values()):
            cmd_args.append("--overwrite")
        cmd_args += [username, remove_flag, folder_path, subfolders_flag] + change_orders

    add_log(f"Lakelady {'download' if download_mode else 'upload'} initiated")
    add_log(f"Change Orders: {', '.join(change_orders)}")
    add_log(f"File path: {folder_path}")
    if download_mode:
        add_log(f"File filter: {file_filter}")
    else:
        add_log(f"Remove existing: {remove_existing}")
    add_log("")
    add_log("Starting browser...")
    add_log("A Firefox window will open. Log in when prompted.")
    add_log("")

    # Launch lakelady.py as a subprocess with unbuffered output
    script_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "lakelady.py")
    cmd = ["python", "-u", script_path] + cmd_args
    if download_mode:
        cmd_display = f'python lakelady.py --download --file-filter {file_filter} {username} False "{folder_path}" False {" ".join(change_orders)}'
    else:
        cmd_display = f'python lakelady.py {username} {remove_flag} "{folder_path}" {subfolders_flag} {" ".join(change_orders)}'
    add_log(f"Command: {cmd_display}")

    try:
        process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            cwd=os.path.dirname(os.path.abspath(__file__)),
            encoding="utf-8",
            errors="replace",
            bufsize=1,  # Line-buffered
        )
        st.session_state.process = process
        add_log(f"Process started (PID: {process.pid})")
    except Exception as e:
        add_log(f"Failed to start process: {e}")
        st.session_state.upload_running = False


# --- Auto-refresh while running ---
if st.session_state.upload_running and st.session_state.process is not None:
    proc = st.session_state.process

    # Read any available output
    read_process_output()

    poll_result = proc.poll()

    if poll_result is None:
        # Process still running - show status and auto-refresh
        st.info("\U0001F504 Lakelady is running...")
        time.sleep(1)
        st.rerun()
    else:
        # Process finished - read any remaining output
        remaining = proc.stdout.read()
        if remaining:
            for line in remaining.strip().split("\n"):
                if line.strip():
                    add_log(line.strip())

        if poll_result == 0:
            add_log("")
            add_log("\U0001F389 Lakelady completed successfully!")
            st.success("Download complete!" if download_mode else "Upload complete!")
        else:
            add_log("")
            add_log(f"\u274C Process exited with code {poll_result}")
            st.error(f"Process exited with code {poll_result}")

        st.session_state.upload_running = False
        st.session_state.process = None


# --- Show log ---
st.subheader("\U0001F4DC Activity Log")
if st.session_state.log_messages:
    log_text = "\n".join(st.session_state.log_messages)
else:
    log_text = "No activity yet."
st.code(log_text, language="text")

# Clear log button
if not st.session_state.upload_running and st.session_state.log_messages:
    if st.button("Clear Log"):
        st.session_state.log_messages = []
        st.rerun()


# --- Footer ---
st.caption(
    "Lakelady v2.1.0 | "
    "Upload: files named with part number prefix (e.g., 400-04463_R01.pdf) | "
    "Download: pulls PDF attachments from affected items | "
    "Supports .png, .jpg, .pdf, .x_t"
)
