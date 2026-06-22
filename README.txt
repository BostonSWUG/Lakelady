Lakelady - Agile PLM File Upload Automation
============================================

Automates uploading SolidWorks export files (images, PDFs, CAD) to Change Orders
in Amazon Robotics Agile PLM.

Files:
    app.py          - Streamlit web UI (run with: streamlit run app.py)
    lakelady.py     - Core automation script (CLI)
    requirements.txt - Python dependencies

Usage (Streamlit UI):
    streamlit run app.py

Usage (Command Line):
    OPTION 1 (full arguments):
        python lakelady.py <username> <True/False> "<path_to_files>" DECO-XXXXX DECO-XXXXX
        arg1: AR username
        arg2: True/False to remove existing attachments in each affd item
        arg3: Path to directory of files to upload (in quotes if spaces)
        arg4+: list of Change Orders

    OPTION 2 (Change Orders only):
        python lakelady.py DECO-XXXXX DECO-XXXXX
        arg1+: list of Change Orders
        * remove_existing_att is set to True by default
        * default path is C:\Solidworks Exports

Dependencies:
    * Python 3.8+
    * Firefox browser + geckodriver in PATH
    * pip install -r requirements.txt

File Naming Convention:
    Files must be named with the part number prefix before an underscore:
        400-04463_R01.pdf
        400-04463_R01.png
        400-04463_R01.x_t

    The part number (400-04463) maps the file to its Affected Item in Agile.

Notes:
    * Change Orders must have Affected Items populated before running
    * Images are automatically cropped to square for Agile thumbnails
    * Supports .png, .jpg, .pdf, .x_t file types
    * .json and .log files are ignored

Authors: Mike Swanson, Graham Silva, Mike Hollis [Goddard Technologies]
         Christopher Pratt [Amazon Robotics]
