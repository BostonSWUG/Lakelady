"""
Lakelady - Agile PLM File Upload Automation

Automates uploading SolidWorks export files (images, PDFs, CAD) to Change Orders
in Amazon Robotics Agile PLM.

Process flow:
    * Gathers list of files in local folder (C:\\Solidworks Exports by default)
    * Opens Agile PLM in Firefox
    * Searches for user-defined Change Order(s)
    * Reads the Affected Items (must be populated before running)
    * For each Affected Item, uploads associated files (.png, .pdf, .x_t)
    * Auto-crops images to square for Agile thumbnail display
    * Optionally removes existing attachments before uploading
    * Iterates through multiple Change Orders if provided

Dependencies:
    * Change Order must have Affected Items already added
    * Files must be in a single folder, named with part number prefix
      (e.g., 400-04463_R01.pdf)

Authors: Mike Swanson, Graham Silva, Mike Hollis [Goddard Technologies]
         Christopher Pratt [Amazon Robotics]
"""

from selenium import webdriver
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.common.by import By
from selenium.webdriver.support.select import Select
from selenium.webdriver.support.wait import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import *
from selenium.webdriver.common.action_chains import ActionChains

from PIL import Image

import os
import sys
import logging
import argparse
import shutil

import time
import traceback


def wait_for_agile_ready(driver, timeout=5):
    """
    Wait for Agile's global progress indicator to become hidden,
    indicating the page has finished loading/processing.

    The indicator is: <span id="progress_indicator_global" style="visibility: hidden;">
    When Agile is loading, visibility changes to "visible".

    :param driver: selenium web driver
    :param timeout: max seconds to wait (default 30)
    :return: None
    """
    try:
        WebDriverWait(driver, timeout).until(
            lambda d: d.execute_script(
                'var el = document.getElementById("progress_indicator_global");'
                'return el && el.style.visibility === "hidden";'
            )
        )
    except Exception:
        # If indicator not found or timeout, continue anyway
        pass


def open_webpage(driver, url="https://arplm.robotics.a2z.com/Agile/PCMServlet"):
    '''
    Opens Agile webpage. Retries if redirected to Cupid/IdPrism SSO
    (which doesn't work with fresh Selenium profiles).
    :param driver: selenium web driver
    :param url: webpage to open, default is Agile
    :return: None
    '''
    max_attempts = 5
    for attempt in range(max_attempts):
        # Clear all browser data before each attempt to avoid stale SSO redirects
        driver.delete_all_cookies()
        try:
            driver.execute_script("window.localStorage.clear();")
            driver.execute_script("window.sessionStorage.clear();")
        except Exception:
            pass  # Can't clear storage on about:blank or restricted pages

        driver.get(url)
        time.sleep(5)  # Wait for page to load/redirect

        # Check if we got redirected to Cupid (which won't work)
        current_url = driver.current_url
        if 'cupid' in current_url or 'idprism' in current_url:
            print(f'  Redirected to Cupid SSO (attempt {attempt + 1}/{max_attempts}), retrying...')
            sys.stdout.flush()
            time.sleep(5)
            continue
        else:
            # Got the correct page - just wait for document ready state
            WebDriverWait(driver, 30).until(
                lambda d: d.execute_script('return document.readyState') == 'complete'
            )
            return

    # If all retries hit Cupid, proceed anyway and let user handle it
    print('  WARNING: Kept getting redirected to Cupid SSO. Proceeding - you may need to authenticate manually.')
    sys.stdout.flush()
    wait_for_agile_ready(driver)


def search_for(driver, xx, params, co, skip_type_select=False):
    '''
    function to search for anything in Agile, use it for COs and ARPN
    :param driver: web element driver
    :param xx: a string to search for in Agile
    :param params: custom details for search, like Items or MPN
            uses:
                ARPN: 'Items'
                Change Orders: 'Changes'
                MFG PN: 'Manufacturer Parts'
                All items: 'All'
    :param co: need to select revision by change order
    :param skip_type_select: if True, skip the search type dropdown (already set)
    :return: none
    '''
    # // *[ @ id = "toggle_search_menu"]
    search_menu_path = '//*[@id="toggle_search_menu"]'
    search_bar_path = '//*[@id="QUICKSEARCH_STRING"]'
    search_button_path = '//*[@id="top_simpleSearch"]'
    rev_id = 'revSelectName'

    # open search menu
    def tmp_func(driver):
        search_menu = WebDriverWait(driver, 10).until(
            EC.element_to_be_clickable((By.XPATH, search_menu_path))
        )
        search_menu.click()

    try_till_works(tmp_func, driver)

    # select search type (skip if already set)
    if not skip_type_select:
        def tmp_func(driver):
            drop_menu = WebDriverWait(driver, 10).until(
                EC.presence_of_element_located((By.ID, "searchmenu"))
            )
            search_type = WebDriverWait(drop_menu, 10).until(
                EC.element_to_be_clickable((By.LINK_TEXT, params))
            )
            search_type.click()

        try_till_works(tmp_func, driver)

    # search for something....
    def tmp_func(driver):
        search_bar = WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.XPATH, search_bar_path))
        )
        search_bar.clear()

        print('searching for: {}'.format(xx))
        logging.info('searching for: {}'.format(xx))

        search_bar.send_keys(xx)
        search_button = WebDriverWait(driver, 10).until(
            EC.element_to_be_clickable((By.XPATH, search_button_path))
        )
        search_button.click()

    try_till_works(tmp_func, driver)
    wait_for_agile_ready(driver)  # Wait for search results to load

    # select revision if searching for an ARPN
    if params == 'Items':
        # get the revision drop down menu element
        rev_drop_down = WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.ID, rev_id))
        )
        rev_drop_down.click()   # click it

        # identify dropdown with Select class
        sel = Select(rev_drop_down)

        try:
            # select by select_by_index() method, not clicking...
            rev = find_rev(sel, co)
            sel.select_by_index(rev)
        except:
            print('rev not selected')
            logging.info('rev not selected')


def find_rev(sel, co):
    '''
    quick loop to get index for proper revision from Select object list
    :param sel: Select class object used for drop-down menus
    :param co: string for co, revision is selected based on Change Order, ex) 'DECO-06583'
    :return: index in drop down options
    '''
    for i in range(0, len(sel.options)):
        dummy = sel.options[i]
        if co in dummy.text:
            print('found rev: {}'.format(dummy.text))
            logging.info('found rev: {}'.format(dummy.text))

            return i
        else:
            print('did not find rev for: {}'.format(co))
            logging.info('did not find rev for: {}'.format(co))

            return None


def check_empty(in_list):
    """
    quick function to check if a list is empty
    :param in_list: list of strings
    :return: True if there's an empty string present in the list
    """
    res = False
    if '' in in_list:
        res = True
    return res


def get_cur_view_affd_items(rows):
    """
    a function to loop through a rows element from HTML table and get
    the affd item text in current view.
    the selenium stuff cannot retrieve the text if it is not visible on the screen.
    this is part of a larger scheme to use page down key to scroll and gather all text
    :param rows: selenium element from an HTML table
    :return: list of affdItems in current view
    """

    # loop through all rows to grab the text
    # if the row is not in current view, it will be empty string
    tmp = []    # list to store the text in the visible rows
    for row in range(1, len(rows)):
        # start range at 1 because the table header comes in blank/empty
        # grab the text from web element and strip empty spaces
        # and check that is not an empty row
        if rows[row].text.strip() != '':
            tmp.append(rows[row].text.strip())
    return tmp


def setup_scroll(driver, ct):
    """
    setup function to enable scrolling by the page down key
    :param driver: selenium web driver object
    :param ct: int, counter for identifying if it is the first pass through the rows, need to click
    :return: body of webpage, or table zone, i forget
    """
    # get body element through CSS_SELECTOR
    body = WebDriverWait(driver, 10).until(
        EC.presence_of_element_located((By.CSS_SELECTOR, 'body'))
    )
    # define the first row path
    first_row_path = '//*[@id="CHANGETABLE_AFFECTEDITEMS"]/tbody/tr[2]/td[1]/div/div[1]/table/tbody/tr[2]/td[1]'
    # get the first row by XPATH
    first_row = WebDriverWait(driver, 10).until(
        EC.presence_of_element_located((By.XPATH, first_row_path))
    )
    if ct == 0:
        first_row.click()  # only click if its first pass
    return body


def get_affd_items(driver):
    """
    get list of affd items in a change order
    it will use function: get_cur_view_affd_items and setup_scroll
    :param driver: webelement driver
    :return: list of affd items (as strings)
    """
    # Click the Affected Items tab - find by link text instead of position
    # (tab position varies between ECO, DECO, MCO types)
    print('  Clicking Affected Items tab...')
    sys.stdout.flush()

    def click_affd_tab(driver):
        # Try finding by link text first (most reliable)
        try:
            element = WebDriverWait(driver, 10).until(
                EC.element_to_be_clickable((By.LINK_TEXT, "Affd Items"))
            )
            element.click()
            return
        except Exception:
            pass

        # Fallback: try "Affected Items" (some CO types use full name)
        try:
            element = WebDriverWait(driver, 5).until(
                EC.element_to_be_clickable((By.LINK_TEXT, "Affected Items"))
            )
            element.click()
            return
        except Exception:
            pass

        # Fallback: partial link text
        try:
            element = WebDriverWait(driver, 5).until(
                EC.element_to_be_clickable((By.PARTIAL_LINK_TEXT, "Affd"))
            )
            element.click()
            return
        except Exception:
            pass

        # Last resort: original positional XPath
        affd_item_tab_path = '//*[@id="tabsDiv" and not(@disabled)]/ul/li[2]'
        element = WebDriverWait(driver, 5).until(
            EC.presence_of_element_located((By.XPATH, affd_item_tab_path))
        )
        element.click()

    try_till_works(click_affd_tab, driver)
    wait_for_agile_ready(driver)
    print('  Affected Items tab opened.')
    sys.stdout.flush()

    # get the expand button to list more ARPN
    expand_path = '// *[ @ id = "filter_pop_CHANGETABLE_AFFECTEDITEMS"]'
    element = WebDriverWait(driver, 10).until(
        EC.presence_of_element_located((By.XPATH, expand_path))
    )
    element.click()
    wait_for_agile_ready(driver)
    time.sleep(1.5)  # Wait for table to fully render after expand

    # get count of affd items
    affdItemCtTxt = int(driver.find_element("xpath", '//*[@id="totalCount_CHANGETABLE_AFFECTEDITEMS"]').text)

    # get all rows element - fetch fresh after expand to avoid stale refs
    rows_xpath = '//*[@id="CHANGETABLE_AFFECTEDITEMS"]/tbody/tr[2]/td[1]/div/div[1]/table/tbody/tr'
    rows = driver.find_elements("xpath", rows_xpath)
    affd_items = (len(rows)-1)*['']  # create empty list to stuff the affdItem numbers
    cur_view = get_cur_view_affd_items(rows)    # get affd items from initial current view of table
    in_cur_view = set(cur_view)     # create a set of it, removes duplicates
    ct = 0  # define a counter for identifying how many scrolls we do, its like a window count

    # loop until affd items list is filled up
    while check_empty(affd_items):
        body = setup_scroll(driver, ct)     # setup window for using pagedown
        body.send_keys(Keys.PAGE_DOWN)  # scroll with pagedown
        time.sleep(0.5)  # Wait for scroll to render

        # Re-fetch rows after scroll to avoid stale element references
        rows = driver.find_elements("xpath", rows_xpath)

        new_view = get_cur_view_affd_items(rows)    # get items in new view after scrolled down
        in_new_view = set(new_view)

        '''
        start to remove any overlap between initial view and new view after scrolled
        '''

        # sort the items that are not accounted for yet
        in_new_not_cur = sorted(in_new_view - in_cur_view)
        # add the new ones to the initial view
        updated_list = cur_view + list(in_new_not_cur)

        # hint: https://www.geeksforgeeks.org/python-merge-overlapping-part-of-lists/
        # iterate from the end of affd_items list and find slice of
        # updated_list that matches the affd_items in order to remove overlap
        temp = (i for i in range(len(updated_list), 0, -1) if updated_list[:i] == list(filter(None, affd_items))[-i:])
        temp2 = next(temp, 0)   # get the first overlap

        # add the new items to our final affd_items using ct as a window of new elements collected
        affd_items[ct:ct+len(updated_list[temp2:])] = updated_list[temp2:]
        # print('updated list: \n')
        ct = ct + len(updated_list[temp2:])      # update count
        cur_view = new_view     # update current view
        in_cur_view = set(cur_view)

    return affd_items


def scan_for_copies(path):
    """
    function to look for copies in a given directory so that we dont have to regenerate the squared files
    :param path: path to directory with files to be uploaded
    :return: list of files that are already squared
    """
    squared = []    # empty list to store file names that are already squared

    # loop through contents of directory
    for file in os.listdir(path):
        f1 = os.fsdecode(file)  # get filename

        e1 = f1.find("-squared")    # get index of keyword
        e2 = f1.find("_")
        # check if it found first keyword, if it wasn't found, .find will return -1
        if e1 > -1:
            p1 = f1[:e2]    # get part number based on e2 index
            # check if squared and add to list
            if "-squared" in f1:
                squared.append(p1)

    # remove duplicates and return as list
    return list(set(squared))


def create_square_image(f_path):
    '''
    - create a single square image, creates copy of orig and saves with -orig suffix.
    - new cropped image retains original file name XXX-XXXXX_R0X.png
    - if image totally sq, does nothing to it, and leaves with original name
    :param fPath: path to a single image file, input should always be an image file
    :return: None
    '''

    file_extension_ignore_list = ["json", "log"]

    picture_extensions = ["png", "jpeg", "jpg"]     # standard image file extensions
    f_dir = os.path.split(f_path)[0]    # get just the directory
    f_name = os.path.split(f_path)[1]   # get just the filename

    # check if orig copy already exists
    if 'orig' in f_path:
        print('orig file already exists...must be a sq counterpart')
        logging.info('orig file already exists...must be a sq counterpart')

        orig = [f_path]
    else:

        # single out the part number
        end_of_part_number = f_name.find("_")

        if end_of_part_number > -1:
            # file name without the extension
            filename_full = f_name[:f_name.find(".")]

            # get just the part number
            part_number_full = f_name[:end_of_part_number]

            # get just the PN Revision _RXX
            # TODO: check revision in filename
            pn_rev = f_name[end_of_part_number+2:f_name.find(".")]

            # check extension for image files
            if f_name.split('.')[-1].lower() in picture_extensions:
                image = Image.open(f_dir + "\\" + f_name)   # load in image with Image package
                if end_of_part_number > -1:
                    w, h = image.size   # get width and height of image
                    # Makes copies only of the images that are not perfect squares
                    if w > h:
                        image.save(f_dir + "\\" + filename_full + "-orig.png")  # save as orig file before processing
                        # do math
                        diff = w - h
                        diff = int(diff / 2)

                        left = diff
                        top = 0
                        right = w - diff
                        bottom = h

                        # crop
                        img_squared = image.crop((left, top, right, bottom))
                        # save file with original filename, no added suffix
                        img_squared.save(f_dir + "\\" + filename_full + ".png")

                    elif h > w:
                        # check other dimension
                        image.save(f_dir + "\\" + filename_full + "-orig.png")  # save as orig file

                        diff = h - w
                        diff = int(diff / 2)

                        left = 0
                        top = diff
                        right = w
                        bottom = h - diff

                        img_squared = image.crop((left, top, right, bottom))
                        img_squared.save(f_dir + "\\" + filename_full + ".png")

                    else:
                        print('image {} already sq... do nothing'.format(filename_full))
                        logging.info('image {} already sq... do nothing'.format(filename_full))


def get_files_to_add(f_path, include_subfolders=False):
    """
    function to get list of file paths to add to agile from a local directory.
    :param f_path: directory with files to add to affd items
    :param include_subfolders: if True, also scan files in subdirectories
    :return: dictionary with affd items as keys and lists of associated filepaths to upload
    """
    import re
    # Match filenames starting with 3-digit prefix + dash (e.g., 400-04463, 405-07872-X)
    # Captures part number = everything before the first underscore or dot
    part_number_pattern = re.compile(r'^(\d{3}-[^_.]+)')

    part_dict = {}  # empty dictionary to store affd items and filepaths
    file_extension_ignore_list = ["json", "log"]

    if include_subfolders:
        # Walk through all subdirectories
        for root, dirs, files in os.walk(f_path):
            for f_name in files:
                filename = os.fsdecode(f_name)
                print('filename: {}'.format(filename))
                logging.info('filename: {}'.format(filename))

                if filename.split('.')[-1].lower() in file_extension_ignore_list:
                    continue

                # Extract part number using regex (handles with or without _R01 suffix)
                match = part_number_pattern.match(filename)
                if match:
                    part_number = match.group(1)
                    if not (part_number in part_dict):
                        part_dict[part_number] = []
                    full_path = os.path.join(root, f_name)
                    part_dict[part_number].append(full_path)
    else:
        # Only scan the top-level directory
        for f_name in os.listdir(f_path):
            filename = os.fsdecode(f_name)
            print('filename: {}'.format(filename))
            logging.info('filename: {}'.format(filename))

            if filename.split('.')[-1].lower() in file_extension_ignore_list:
                continue

            # Extract part number using regex (handles with or without _R01 suffix)
            match = part_number_pattern.match(filename)
            if match:
                part_number = match.group(1)
                if not (part_number in part_dict):
                    part_dict[part_number] = []
                full_path = os.path.join(f_path, f_name)
                part_dict[part_number].append(full_path)

    # Move image attachments to the beginning of the list, so they get uploaded first
    for cur_key in part_dict:
        # print('cur key in part_dict: {}'.format(cur_key))

        # loop through all filepaths for the current key in the dict
        cur_index = 0
        while cur_index < len(part_dict[cur_key]):
            # check if it has image file ext
            if part_dict[cur_key][cur_index].split('.')[-1].lower() in ['png', 'jpg', 'jpeg']:
                # move filepath to start of list
                part_dict[cur_key].insert(0, part_dict[cur_key].pop(cur_index))
            cur_index += 1

    return part_dict


def try_till_works(in_fuction, driver, optional=None, swtch=True):
    """
    Continually tries to run a function until it has no error.
    This is a pretty hacky way to do things, but its also very consistent, which is what's important.
    :param in_fuction: function to pass through and run till it works
    :param driver: selenium web driver object
    :param optional: specific options, like for passing through the in_function
    :param swtch: need to switch to a different set of web driver content?
    :return: None
    """
    stay = True
    start_time = time.time()
    timeout = 15  # 15 seconds max retry window
    last_error = None

    while stay and (time.time() - start_time < timeout):
        try:
            if swtch:
                driver.switch_to.default_content()

            if optional is None:
                in_fuction(driver)
            else:
                in_fuction(driver, optional)

            stay = False
        except Exception as e:
            last_error = e
            time.sleep(0.1)

    if stay and last_error:
        print(f'    WARNING: try_till_works timed out after {timeout}s: {type(last_error).__name__}')
        logging.warning(f'try_till_works timed out: {last_error}')


def download_from_affd_item(driver, co, affd_item, ct, download_path, file_filter="pdf", overwrite=False):
    """
    Download attachments from a single Affected Item.

    :param driver: selenium web driver
    :param co: change order number (e.g., DECO-19364)
    :param affd_item: the AR-PN to download attachments from
    :param ct: index for progress tracking
    :param download_path: local directory to save downloaded files
    :param file_filter: file extension filter (default "pdf"), or "all" for everything
    :param overwrite: if True, delete existing files before download; if False, Firefox appends (1), (2)
    :return: list of downloaded file names
    """
    # Search for the affected item (search type already set to Items)
    search_for(driver, affd_item, 'Items', co, skip_type_select=True)
    wait_for_agile_ready(driver)

    print(f'    Navigating to Attachments tab for {affd_item}...')
    sys.stdout.flush()

    # Go to attachments tab
    def tmp_func(driver):
        element = WebDriverWait(driver, 20).until(
            EC.element_to_be_clickable((By.LINK_TEXT, "Attachments"))
        )
        element.click()

    try_till_works(tmp_func, driver)
    wait_for_agile_ready(driver)

    # Get the attachment file list
    downloaded = []
    try:
        footer_path = '//*[@id="table_footer"]'
        element = WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.XPATH, footer_path))
        )
        num_files = int(element.text.split()[2])

        if num_files == 0:
            print(f'    No attachments found for {affd_item}.')
            sys.stdout.flush()
            return downloaded

        print(f'    Found {num_files} attachment(s). Looking for {file_filter} files...')
        sys.stdout.flush()

        # Get all attachment links in the file list table
        att_table_path = '//*[@id="ATTACHMENTS_FILELIST"]'
        att_table = WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.XPATH, att_table_path))
        )

        # Find all download links (anchor tags with file names)
        links = att_table.find_elements(By.TAG_NAME, "a")

        for link in links:
            link_text = link.text.strip()
            if not link_text:
                continue

            # Check file extension filter
            if file_filter != "all":
                # Support comma-separated filters like "pdf,png"
                allowed_exts = [ext.strip().lower() for ext in file_filter.split(",")]
                file_ext = link_text.rsplit(".", 1)[-1].lower() if "." in link_text else ""
                if file_ext not in allowed_exts:
                    continue

            # Click the link to download
            try:
                # If overwrite mode, delete existing file first
                if overwrite:
                    existing_file = os.path.join(download_path, link_text)
                    if os.path.exists(existing_file):
                        os.remove(existing_file)

                # Click the attachment link - Agile serves the file directly
                driver.execute_script("arguments[0].click();", link)
                time.sleep(3)  # Wait for download to start/complete

                # Firefox downloads to browser.download.dir (the base path).
                # If download_path is a subfolder, move the file there.
                firefox_download_dir = os.path.dirname(download_path)
                src_file = os.path.join(firefox_download_dir, link_text)
                dest_file = os.path.join(download_path, link_text)
                if os.path.normpath(src_file) != os.path.normpath(dest_file):
                    # Wait for download to finish (no .part file remaining)
                    part_file = src_file + ".part"
                    wait_start = time.time()
                    while os.path.exists(part_file) and (time.time() - wait_start < 30):
                        time.sleep(0.5)
                    if os.path.exists(src_file):
                        shutil.move(src_file, dest_file)

                downloaded.append(link_text)
                print(f'    Downloaded: {link_text}')
                sys.stdout.flush()
                logging.info(f'Downloaded: {link_text} from {affd_item}')
            except Exception as e:
                print(f'    Could not download {link_text}: {e}')
                sys.stdout.flush()
                logging.warning(f'Could not download {link_text}: {e}')

    except Exception as e:
        print(f'    Error reading attachments for {affd_item}: {e}')
        logging.warning(f'Error reading attachments for {affd_item}: {e}')

    return downloaded


def upload_to_affd_item(driver, co, affd_item, file_paths, ct, remove_existing_att):
    """
    function to upload multiple files to a single Affd Item

    :param driver: webelement driver
    :param co: change order, ex DECO-010101
    :param affd_item: the AR-PN that is an affected item for which docs need to be uploaded to
    :param file_paths: a list of file paths for the files to upload.
                       standard files will be .png, .pdf, .x_t, not in that order
    :param ct: index for number of affd item in the total list of affd items for the change order
    :param remove_existing_att: boolean to remove all existing attachments in an affd item
    :return: None
    :TODO:  check if there is a file type missing for a particular affd item...
            ie. only png file is in folder but need the others!
    """

    # instead of clicking on each Affd Item, just search for it
    search_type = 'Items'   # specify to search for an item, like a PN, not change order
    search_for(driver, affd_item, search_type, co)  # do the search, specify CO as option to select the revision
    wait_for_agile_ready(driver)  # Wait for page to load after revision selection

    print(f'    Step 1: Clicking Attachments tab...')
    sys.stdout.flush()

    # go to attachments tab
    def tmp_func(driver):
        element = WebDriverWait(driver, 20).until(
            EC.element_to_be_clickable((By.LINK_TEXT, "Attachments"))
        )
        element.click()

    try_till_works(tmp_func, driver)
    wait_for_agile_ready(driver)
    print(f'    Step 2: Attachments tab loaded.')
    sys.stdout.flush()

    # check if there's any files already uploaded
    if remove_existing_att:
        print(f'    Step 2b: Checking for existing attachments to remove...')
        sys.stdout.flush()

        def tmp_func(driver):
            f = '//*[@id="table_footer"]'
            element = WebDriverWait(driver, 20).until(EC.presence_of_element_located((By.XPATH, f)))
            num_existing_files = int(element.text.split()[2])

            # if files already there, remove them
            if num_existing_files > 0:
                print(f'    Removing {num_existing_files} existing attachment(s)...')
                sys.stdout.flush()
                pp = '//*[@id="ATTACHMENTS_FILELIST"]'
                attch_list = driver.find_element(By.XPATH, pp)
                all_td = attch_list.find_elements(By.XPATH, ".//td")
                for t_d in all_td:
                    att = t_d.get_attribute("class")
                    if att == ' GPanelTopHeader GMCellHeaderPanel':
                        t_d.click()
                        time.sleep(0.2)

                remove_button_path = '//*[@id="MSG_Remove_5"]'
                remove_button = WebDriverWait(driver, 10).until(
                    EC.presence_of_element_located((By.XPATH, remove_button_path)))
                remove_button.click()
                wait_for_agile_ready(driver)  # Wait for removal to complete
            else:
                print(f'    No existing attachments to remove.')
                sys.stdout.flush()

        try_till_works(tmp_func, driver)

    print(f'    Step 3: Opening Add Attachment dialog...')
    sys.stdout.flush()

    # open add attachment window - retry up to 3 times
    dialog_opened = False
    for attempt in range(3):
        def tmp_func(driver):
            element = WebDriverWait(driver, 20).until(
                EC.element_to_be_clickable((By.ID, "MSG_AddAttachment_5")))
            element.click()

        try_till_works(tmp_func, driver)
        wait_for_agile_ready(driver)

        # Check if dialog actually opened
        try:
            element = WebDriverWait(driver, 10).until(
                EC.presence_of_element_located((By.ID, "lf_add_palette_subtitle"))
            )
            dialog_opened = True
            break
        except Exception:
            print(f'    Dialog did not open (attempt {attempt + 1}/3), retrying...')
            sys.stdout.flush()
            wait_for_agile_ready(driver)

    if not dialog_opened:
        print(f'    ERROR: Could not open Add Attachment dialog after 3 attempts.')
        sys.stdout.flush()
        logging.error('Could not open Add Attachment dialog')
        return

    print(f'    Step 4: Upload dialog open.')
    sys.stdout.flush()

    # get the subtitle to verify correct affd item
    element = WebDriverWait(driver, 10).until(
        EC.presence_of_element_located((By.ID, "lf_add_palette_subtitle"))
    )
    affd_item_check = element.text    # get text for affd item from upload window subtitle

    # check that it is the correct Affd Item
    if affd_item == affd_item_check:
        file_extensions = ["png", "jpg", "jpeg", "pdf", "x_t"]   # define all ext to upload
        img_ext = ["png", "jpg", "jpeg"]

        ct = 0  # define a counter for number of files uploaded per affd item

        # loop through file paths
        for f in file_paths:
            part_number = os.path.split(f)[1].split("_")[0]     # get affd item, PN
            f_ext = os.path.split(f)[1].split(".")[1]           # get file ext

            # check again if the path PN matches affd item
            if part_number == affd_item:
                # check if its an image file, need to make square
                if f_ext in file_extensions[0:2]:
                    create_square_image(f)  # make square
                # check that it is not the original 'unsquare' image file AND acceptable file ext
                # this is a catch-all for all files
                if 'orig' not in f and f_ext in file_extensions:
                    ct += 1     # increment ct for number of files uploading...
                    print('uploading file: {}'.format(f))
                    logging.info('uploading file: {}'.format(f))

                    # get the web element object for adding file paths too for upload
                    def tmp_func(driver, f):
                        element = WebDriverWait(driver, 20).until(
                            EC.presence_of_element_located((By.ID, "add-files-input")))
                        element.send_keys(f)
                        time.sleep(1)  # Brief wait for file to register in upload list

                    try_till_works(tmp_func, driver, optional=f)    # need to specific file path here
            else:
                print('file is not for this affd item')
                logging.info('file is not for this affd item')

        print('\tuploaded {} files'.format(ct))
        logging.info('uploaded {} files'.format(ct))

        # click upload button
        def tmp_func(driver):
            element = WebDriverWait(driver, 10).until(
                EC.element_to_be_clickable((By.ID, "uploadFilesUM")))
            element.click()

        try_till_works(tmp_func, driver)
        wait_for_agile_ready(driver)

        # wait for upload to complete (best-effort check)
        time.sleep(2)  # Brief pause for upload processing
        try:
            pp = '/html/body/div[6]/div[1]/div/div[2]/div[1]/table/tbody'
            el_start = driver.find_element(By.XPATH, pp)
            col_el = el_start.find_elements(By.XPATH, '//*[@id="completed"]')
            if len(col_el) >= ct:
                print(f'    Upload verified: {ct} file(s) completed.')
                logging.info(f'Upload verified: {ct} files completed')
            else:
                print(f'    Upload sent ({ct} files) - verification inconclusive.')
                logging.info(f'Upload sent but verification inconclusive')
        except Exception:
            print(f'    Upload sent ({ct} files) - could not verify completion status.')
            logging.info('Upload sent, verification skipped')

        # close upload manager
        def tmp_func(driver):
            element = WebDriverWait(driver, 10).until(
                EC.element_to_be_clickable((By.ID, "lfuploadpalette_window_close")))
            element.click()

        try_till_works(tmp_func, driver)
        wait_for_agile_ready(driver)

    else:
        # TODO: try to upload to this affd item again
        print('affd item mismatch in the upload window...')
        logging.info('affd item mismatch in the upload window...')


def login_to_agile_auto(driver, username='zswanmic', pword_file=r"C:\tmp\pword.txt"):
    """
    function to login automatically into Agile.  less secure
    :param driver: selenium web driver
    :param username: AR username
    :param pword_file: a file that contains your password, default path is C:\\tmp\\pword.txt
    :return: None
    """
    # find username box
    username_path = '//*[@id="j_username"]'
    pword_path = '//*[@id="j_password"]'

    user_entry = WebDriverWait(driver, 10).until(
        EC.presence_of_element_located((By.XPATH, username_path))
    )
    print('Username to Agile')
    logging.info('Username to Agile')

    user_entry.send_keys(username)

    # Reads password from a text file because
    # saving the password in a script is just silly.
    with open(pword_file, 'r') as myfile:
        pword = myfile.read().replace('\n', '')\

    pword_entry = WebDriverWait(driver, 10).until(
        EC.presence_of_element_located((By.XPATH, pword_path))
    )
    # pword_entry = driver.find_element("xpath", (pword_path))
    pword_entry.send_keys(pword)
    print('Pword to Agile')
    logging.info('Pword to Agile')

    login_path = '//*[@id="login"]'
    login_button = WebDriverWait(driver, 10).until(
        EC.presence_of_element_located((By.XPATH, login_path))
    )
    # login_button = driver.find_element("xpath", (login_path))
    login_button.click()
    print('Logging into Agile......')
    logging.info('Logging into Agile......')

    # Close the extra Agile window
    driver.close()
    # Wait for action to complete
    while len(driver.window_handles) > 1:
        time.sleep(0.1)
    # Make the correct window the active window and wait for page to load
    driver.switch_to.window(driver.window_handles[0])
    # getTargetWindow(driver)


def login_to_agile(driver, username):
    """
    Handles the Agile login flow. Fills in the username and waits for login
    to complete. Supports both:
      - Manual login (user types password, clicks Login)
      - Automatic/SSO login (certificate or SSO handles auth)

    Login completion is detected by either:
      1. A second window opening (old Agile behavior) — closes it and switches back
      2. The post-login page loading (search bar appears)

    :param driver: selenium web driver
    :param username: AR username
    :return: None
    """
    # Wait for the login page to load (up to 60 seconds)
    print("  Waiting for Agile login page...")
    sys.stdout.flush()

    try:
        WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.XPATH, '//*[@id="j_username"]'))
        )
        # Fill in username
        user_entry = driver.find_element(By.XPATH, '//*[@id="j_username"]')
        user_entry.clear()
        user_entry.send_keys(username)
        print(f"  Username '{username}' entered.")
        sys.stdout.flush()
    except Exception:
        # Login page might have been skipped (SSO), or already logged in
        print("  Login page not found - may have auto-authenticated via SSO.")
        sys.stdout.flush()

    # Wait for login to complete by checking two conditions:
    # 1. A second window opens (old Agile behavior)
    # 2. The post-login search bar appears (modern/SSO behavior)
    print("  Waiting for login to complete...")
    sys.stdout.flush()

    start_time = time.time()
    timeout = 120  # 2 minutes

    while time.time() - start_time < timeout:
        # Check if a second window opened (old behavior)
        if len(driver.window_handles) > 1:
            print("  Second window detected - closing extra window...")
            driver.close()
            while len(driver.window_handles) > 1:
                time.sleep(0.1)
            driver.switch_to.window(driver.window_handles[0])
            print("  Login complete!")
            sys.stdout.flush()
            return

        # Check if we're already on the post-login page (SSO/auto-login)
        try:
            driver.find_element(By.XPATH, '//*[@id="QUICKSEARCH_STRING"]')
            print("  Login complete (search bar detected)!")
            sys.stdout.flush()
            return
        except Exception:
            pass

        time.sleep(0.5)

    print("  WARNING: Login wait timed out (2 min). Proceeding anyway.")
    sys.stdout.flush()


def get_target_window(driver):
    """
    handles getting the target window with selenium driver... not used in this version,
    but could be useful later...
    :param driver:
    :return:
    """
    init_window = driver.window_handles[0]
    print('init window: {}'.format(init_window))
    target_window = driver.window_handles[1]
    print('target window: {}'.format(target_window))
    driver.close()      # close initial window
    driver.switch_to.window(target_window)
    print('current window: {}'.format(driver.current_window_handle))


def run_me():
    '''
    Lakelady - Agile PLM File Upload Automation

    Main function that handles user defined inputs and runs the upload sequence from cmd line.

    Usage:
        OPTION 1 (full args):
            python lakelady.py <username> <True/False> "<path_to_files>" DECO-XXXXX DECO-XXXXX
            arg1: AR username
            arg2: True/False to remove existing attachments in each affd item
            arg3: Path to directory of files to upload (in quotes if spaces)
            arg4+: list of Change Orders

        OPTION 2 (COs only):
            python lakelady.py DECO-XXXXX DECO-XXXXX
            arg1+: list of Change Orders
            * remove_existing_att is set to True by default
            * default path is C:\\Solidworks Exports

    :return: None
    '''

    # Argument parsing
    parser = argparse.ArgumentParser(
        prog='lakelady',
        description='Lakelady - Automate file uploads/downloads to Agile PLM Change Orders',
    )
    parser.add_argument('strings', nargs='+',
                        help='Username, remove flag, path, and Change Order numbers (see --help)')
    parser.add_argument('--download', action='store_true',
                        help='Download mode: download PDF attachments from affected items instead of uploading')
    parser.add_argument('--file-filter', default='pdf',
                        help='File extension to download (default: pdf). Use "all" for all files.')
    parser.add_argument('--create-subfolders', action='store_true',
                        help='Create a subfolder named after each CO within the download path')
    parser.add_argument('--overwrite', action='store_true',
                        help='Overwrite existing files during download (default: append number suffix)')
    args = parser.parse_args()

    # Default values
    path_with_files = r'C:\Solidworks Exports'
    username = ''
    remove_existing_att = True
    include_subfolders = False
    change_orders = []
    download_mode = args.download
    file_filter = args.file_filter

    # Parse arguments based on pattern
    # A Change Order looks like: DECO-XXXXX, ECO-XXXXX, MCO-XXXXX (prefix-digits)
    import re
    co_pattern = re.compile(r'^[A-Z]+-\d+$')

    def is_change_order(s):
        """Check if a string looks like a Change Order number."""
        return bool(co_pattern.match(s))

    if not is_change_order(args.strings[0]):
        # Full args: username, remove_flag, path, subfolders_flag, COs...
        username = args.strings[0]
        remove_existing_att = args.strings[1].lower() in ('true', '1', 'yes')

        # Check if arg3 is a path or a CO
        if len(args.strings) > 2 and not is_change_order(args.strings[2]):
            path_with_files = args.strings[2]
            # Check if arg4 is the subfolders flag or a CO
            if len(args.strings) > 3 and args.strings[3].lower() in ('true', 'false', '1', '0', 'yes', 'no'):
                include_subfolders = args.strings[3].lower() in ('true', '1', 'yes')
                change_orders = args.strings[4:]
            else:
                change_orders = args.strings[3:]
        else:
            change_orders = args.strings[2:]
    else:
        # COs only
        change_orders = args.strings

    # Setup logging
    time_string = time.strftime("%Y-%m-%d_%H%M%S", time.localtime())
    log_file = os.path.join(path_with_files, 'lakelady_log.txt') if os.path.exists(path_with_files) else 'lakelady_log.txt'
    logging.basicConfig(filename=log_file, format='%(levelname)s:%(message)s', level=logging.INFO)

    print('Lakelady - Agile PLM Upload Tool')
    print('=' * 40)
    print(f'Time: {time_string}')
    print(f'Mode: {"DOWNLOAD" if download_mode else "UPLOAD"}')
    print(f'Username: {username or "(manual login)"}')
    print(f'Remove existing: {remove_existing_att}')
    print(f'Include subfolders: {include_subfolders}')
    print(f'File path: {path_with_files}')
    print(f'Change Orders: {change_orders}')
    if download_mode:
        print(f'File filter: {file_filter}')
    print('=' * 40)
    sys.stdout.flush()

    logging.info(f'\n-----\nLakelady new log\n{time_string}')
    logging.info(f'Change Orders: {change_orders}')
    logging.info(f'Path: {path_with_files}')

    affd_items = []

    if not os.path.exists(path_with_files):
        print(f'ERROR: Path does not exist: {path_with_files}')
        logging.error(f'Path does not exist: {path_with_files}')
        sys.exit(1)

    print(f'path exists...\n\t{path_with_files}')
    logging.info(f'path exists...\n\t{path_with_files}')

    # Flush output so header appears before browser launches
    sys.stdout.flush()

    driver = None
    try:
        # Launch Firefox browser with options to prevent profile conflicts
        from selenium.webdriver.firefox.options import Options as FirefoxOptions
        firefox_options = FirefoxOptions()
        firefox_options.add_argument("--no-remote")  # Prevent connecting to existing Firefox

        # Configure download directory for download mode
        if download_mode:
            # Always set Firefox download dir to the BASE path.
            # Files will be moved to per-CO subfolders after download.
            download_dir = os.path.abspath(path_with_files)
            os.makedirs(download_dir, exist_ok=True)
            firefox_options.set_preference("browser.download.folderList", 2)
            firefox_options.set_preference("browser.download.dir", download_dir)
            firefox_options.set_preference("browser.download.useDownloadDir", True)
            firefox_options.set_preference("browser.helperApps.neverAsk.saveToDisk",
                                          "application/pdf,application/octet-stream,application/x-pdf,"
                                          "application/force-download,application/x-download,"
                                          "image/png,image/jpeg,image/jpg,"
                                          "application/x-parasolid,model/x_t")
            firefox_options.set_preference("pdfjs.disabled", True)  # Don't open PDFs in browser
            firefox_options.set_preference("browser.download.manager.showWhenStarting", False)
            print(f"  Download directory set to: {download_dir}")
            sys.stdout.flush()

        print("Launching Firefox...")
        sys.stdout.flush()
        driver = webdriver.Firefox(options=firefox_options)

        # Ensure we have a valid window handle before navigating
        time.sleep(1)
        if not driver.window_handles:
            print("ERROR: No browser window available after launch.")
            sys.exit(1)
        driver.switch_to.window(driver.window_handles[0])

        # Open the Agile webpage
        print(f"Navigating to Agile...")
        sys.stdout.flush()
        open_webpage(driver)

        # Login - prompts user to enter password manually
        print("Please log in via the browser window...")
        sys.stdout.flush()
        login_to_agile(driver, username)
        wait_for_agile_ready(driver)  # Wait for post-login page to fully load

        for co_x, co in enumerate(change_orders):
            print(f'\n{"="*40}')
            print(f'Change Order ({co_x+1} of {len(change_orders)}): {co}')
            print(f'{"="*40}')
            logging.info(f'Working on CO ({co_x+1}/{len(change_orders)}): {co}')

            search_type = 'Changes'
            search_for(driver, co, search_type, '')

            if not affd_items:
                affd_items = get_affd_items(driver)
                print(f'Affected Items from Agile: {affd_items}')
                logging.info(f'Affected Items: {affd_items}')
            else:
                print(f'User-defined Affected Items: {affd_items}')
                logging.info(f'User-defined Affected Items: {affd_items}')

            if download_mode:
                # DOWNLOAD MODE: download attachments from each affected item
                if args.create_subfolders:
                    co_download_path = os.path.abspath(os.path.join(path_with_files, co))
                else:
                    co_download_path = os.path.abspath(path_with_files)
                os.makedirs(co_download_path, exist_ok=True)
                print(f'Download folder: {co_download_path}')
                logging.info(f'Download folder: {co_download_path}')

                # Set search type to Items once (Agile remembers the selection)
                def set_search_type_items(driver):
                    search_menu = WebDriverWait(driver, 10).until(
                        EC.element_to_be_clickable((By.XPATH, '//*[@id="toggle_search_menu"]'))
                    )
                    search_menu.click()
                    drop_menu = WebDriverWait(driver, 10).until(
                        EC.presence_of_element_located((By.ID, "searchmenu"))
                    )
                    items_option = WebDriverWait(drop_menu, 10).until(
                        EC.element_to_be_clickable((By.LINK_TEXT, "Items"))
                    )
                    items_option.click()

                try_till_works(set_search_type_items, driver)
                print('  Search type set to Items.')
                sys.stdout.flush()

                ct = 0
                total_downloaded = 0
                for affd_item in affd_items:
                    ct += 1
                    print(f'  [{ct}/{len(affd_items)}] Checking attachments for {affd_item}...')
                    sys.stdout.flush()
                    logging.info(f'Downloading from affd_item ({ct}/{len(affd_items)}): {affd_item}')
                    downloaded = download_from_affd_item(driver, co, affd_item, ct, co_download_path, file_filter, args.overwrite)
                    total_downloaded += len(downloaded)

                print(f'\n*** {co} DOWNLOAD COMPLETE: {total_downloaded} file(s) ***')
                sys.stdout.flush()
                logging.info(f'{co} download complete: {total_downloaded} files')

            else:
                # UPLOAD MODE: upload files to each affected item
                f_paths = get_files_to_add(path_with_files, include_subfolders)

                ct = 0
                for affd_item in affd_items:
                    ct += 1
                    print(f'  [{ct}/{len(affd_items)}] Uploading to {affd_item}...')
                    logging.info(f'Working on affd_item ({ct}/{len(affd_items)}): {affd_item}')
                    if affd_item in f_paths:
                        upload_to_affd_item(driver, co, affd_item, f_paths[affd_item], ct, remove_existing_att)
                    else:
                        print(f'    No files found for {affd_item}, skipping.')
                        logging.info(f'No files for {affd_item}')

                print(f'\n*** {co} UPLOAD COMPLETE ***')
                logging.info(f'{co} upload complete')

            # Navigate back to CO
            search_for(driver, co, 'Changes', '')

            # Reset affd_items for next CO
            affd_items = []

        print('\n' + '=' * 40)
        print(f'ALL {"DOWNLOADS" if download_mode else "UPLOADS"} COMPLETE')
        print('=' * 40)
        logging.info('All operations complete')

        # Close the browser
        if driver:
            driver.quit()

    except Exception as e:
        print(f'\nERROR: {type(e).__name__}: {e}')
        logging.exception('Upload failed')
        traceback.print_exc()
        if driver:
            try:
                driver.quit()
            except Exception:
                pass
        sys.exit(1)


def main():
    run_me()


if __name__ == "__main__":
    main()
