import yaml
import argparse
import json
import requests
import os
import re
import mimetypes
import datetime
import logging

from bs4 import BeautifulSoup, CData
from pathlib import Path
from random import seed
from random import randint


def get_element_attribute(element, attribute_name, default_value=''):
    try:
        result = element[attribute_name]
    except:
        result = default_value
    return result


def create_simple_tag(soup, tag_type, tag_text):
    tag = soup.new_tag(tag_type)
    tag.string = tag_text
    return tag


def get_element_attribute(element, attribute_name, default_value=''):
    try:
        result = element[attribute_name]
    except:
        result = default_value
    return result


def create_simple_tag(soup, tag_type, tag_text):
    tag = soup.new_tag(tag_type)
    tag.string = tag_text
    return tag


class ConfluencePage:
    name_cache = {'root': 1}

    def __init__(self, title, page_id="", parent_id="", html_content="", uuid=""):
        self.parentId = parent_id
        self.id = page_id
        self.set_content(html_content)
        self.update_title(title)
        self.children = []
        self.images = []
        self.attachments = []
        self.uuid = uuid
        self.labelsMetadata = None

    def add_child(self, confluencePage):
        self.children.append(confluencePage)

    def set_parent(self, parent_id):
        self.parentId = parent_id

    def set_id(self, page_id):
        self.id = page_id
        for child in self.children:
            child.set_parent(self.id)

    def set_content(self, content):
        soup = BeautifulSoup(content, 'html.parser')
        for img in soup.findAll('img'):
            src = img.get('src', '')
            if src:
                filename = os.path.basename(src)
                # Skip images with very long URLs (likely external URLs with tokens)
                if len(filename) > 255 or '?' in filename:
                    logging.warning(f'WARNING - Skipping image with problematic filename in card "{self.title}": {filename[:100]}...')
                    continue
                self.images.append(filename)
        for attachment in soup.findAll('a'):
            href = get_element_attribute(attachment, 'href', '')
            if href.startswith('resources/'):
                filename = os.path.basename(href)
                # Skip attachments with very long filenames
                if len(filename) > 255 or '?' in filename:
                    logging.warning(f'WARNING - Skipping attachment with problematic filename in card "{self.title}": {filename[:100]}...')
                    continue
                self.attachments.append(filename)
            if 'getguru.com' in href:
                logging.warning('WARNING - Card "{}" contains reference to getguru.com'.format(self.title))
        # Guru exports code blocks as <pre> with one inline <code> element per
        # line (no newlines between them). Passed through unchanged, Confluence
        # collapses the lines and parses code as HTML. Convert each block to a
        # Confluence "code" macro with the source in a CDATA plain-text-body.
        for pre in soup.findAll("pre"):
            code_lines = pre.findAll("code")
            if code_lines:
                code_text = "\n".join(line.get_text() for line in code_lines)
            else:
                code_text = pre.get_text()

            code_macro = soup.new_tag("ac:structured-macro")
            code_macro["ac:name"] = "code"
            code_macro["ac:schema-version"] = "1"

            language = get_element_attribute(pre, "data-ghq-code-block-prism", "")
            if language:
                lang_param = soup.new_tag("ac:parameter")
                lang_param["ac:name"] = "language"
                lang_param.string = language
                code_macro.append(lang_param)

            body = soup.new_tag("ac:plain-text-body")
            body.append(CData(code_text))
            code_macro.append(body)
            pre.replace_with(code_macro)
        for ruler in soup.findAll('hr'):
            ruler_new = soup.new_tag('hr')
            ruler.replaceWith(ruler_new)
        for iframe in soup.findAll('iframe'):
            src = get_element_attribute(iframe, 'src', '')
            width = get_element_attribute(iframe, 'width', '100%')
            height = get_element_attribute(iframe, 'height', '630')
            iframe_new = soup.new_tag('ac:structured-macro')
            iframe_new['ac:name'] = 'iframe'
            iframe_new['ac:schema-version'] = '1'
            iframe_new['data-layout'] = 'default'
            iframe_new_param1 = soup.new_tag('ac:parameter')
            iframe_new_param1['ac:name'] = 'src'
            iframe_new_param1_url = soup.new_tag('ri:url')
            iframe_new_param1_url['ri:value'] = src
            iframe_new_param1.append(iframe_new_param1_url)
            iframe_new.append(iframe_new_param1)
            iframe_new_param2 = soup.new_tag('ac:parameter')
            iframe_new_param2['ac:name'] = 'width'
            iframe_new_param2.string = width
            iframe_new.append(iframe_new_param2)
            iframe_new_param3 = soup.new_tag('ac:parameter')
            iframe_new_param3['ac:name'] = 'height'
            iframe_new_param3.string = height
            iframe_new.append(iframe_new_param3)
            iframe.replace_with(iframe_new)

        self.htmlContent = str(soup)

    def update_title(self, title):
        title_candidate = title.replace("&", " and ").encode("utf-8", "ignore").decode()
        if title_candidate in ConfluencePage.name_cache.keys():
            num_occurence = int(ConfluencePage.name_cache[title_candidate]) + 1
            self.title = title_candidate + " (in multiple boards " + str(num_occurence) + ")"
            ConfluencePage.name_cache.update({title_candidate: num_occurence})
        else:
            self.title = title_candidate
            ConfluencePage.name_cache.update({title_candidate: 1})

    def update_labels(self, tags):
        if tags is None:
            self.labelsMetadata = None
        else:
            labelsJson = []
            for label in tags:
                restrictedCharacters = [":", ";", ",", ".", "?", "&", "[", "]", "(", ")", "#", "^", "*", "@", "!", " "]
                for restrictedCharacter in restrictedCharacters:
                    label = label.replace(restrictedCharacter, "-")
                nameJson = {"prefix": "global", "name": "{}".format(label)}
                labelsJson.append(nameJson)
            self.labelsMetadata = labelsJson

    def replace_img_with_confluence_image(self):
        soup = BeautifulSoup(self.htmlContent, 'html.parser')
        for img in soup.findAll('img'):
            filename = os.path.basename(img['src'])
            soup_ac_image = BeautifulSoup("<ac:image><ri:attachment ri:filename=\"" + filename + "\" /></ac:image>",
                                          'html.parser')
            img.replace_with(soup_ac_image)
        self.htmlContent = str(soup)

    def replace_att_with_confluence_attachment(self):
        soup = BeautifulSoup(self.htmlContent, 'html.parser')
        for attachment in soup.findAll('a'):
            href = get_element_attribute(attachment, 'href', '')
            if href.startswith('resources/'):
                filename = os.path.basename(href)
                attachment_new = soup.new_tag('ac:structured-macro')
                attachment_new['ac:name'] = 'view-file'
                attachment_new_param1 = soup.new_tag('ac:parameter')
                attachment_new_param1['ac:name'] = 'name'
                attachment_new_ri = soup.new_tag('ri:attachment')
                attachment_new_ri['ri:filename'] = filename
                attachment_new_param1.append(attachment_new_ri)
                attachment_new.append(attachment_new_param1)
                attachment.replace_with(attachment_new)

        self.htmlContent = str(soup)

    def __str__(self):
        obj = {"title": self.title, "id": self.id, "parent": self.parentId, "children": [], "images": []}
        for child in self.children:
            raw = json.dumps(child, default=lambda o: o.__dict__)
            obj["children"].append(json.loads(raw))
        for image in self.images:
            raw = json.dumps(image, default=lambda o: o.__dict__)
            obj["images"].append(json.loads(raw))
        return json.dumps(obj, default=lambda o: o.__dict__)


def create_confluence_page(organization, space, parent, user_name, user_credentials, title, content):
    url = "https://" + organization + ".atlassian.net/wiki/rest/api/content"
    data = {
        "title": title,
        "type": "page",
        "space": {
            "key": space
        },
        "status": "current",
        "ancestors": [
            {
                "id": parent
            }
        ],
        "body": {
            "storage": {
                "value": content,
                "representation": "storage"
            }
        },
        "metadata": {
            "properties": {
                "editor": {
                    "value": "v2"
                }
            }
        }
    }
    headers = {'Content-Type': 'application/json', 'Accept': 'application/json'}
    session = requests.Session()
    session.auth = (user_name, user_credentials)
    raw_response = session.post(url, data=json.dumps(data), headers=headers)
    if not raw_response.ok:
        if raw_response.status_code == 400:
            if 'a page already exists with the same title in this space' in raw_response.text.lower():
                logging.warning('DUPLICATE TITLE - {}'.format(title))
        else:
            logging.error("ERROR from API create request: " + str(raw_response.status_code))
            logging.error("ERROR data: " + str(data))
            logging.error("ERROR response: " + str(raw_response.text))

    response = raw_response.json()
    return response


def get_confluence_page_by_title(organization, space, user_name, user_credentials, title, parent_id=None):
    """
    Search for a Confluence page by title in a specific space.
    Returns the page info if found, None otherwise.
    """
    url = "https://" + organization + ".atlassian.net/wiki/rest/api/content"
    params = {
        "spaceKey": space,
        "title": title,
        "expand": "version"
    }
    headers = {'Content-Type': 'application/json', 'Accept': 'application/json'}
    session = requests.Session()
    session.auth = (user_name, user_credentials)
    
    try:
        raw_response = session.get(url, params=params, headers=headers)
        if raw_response.ok:
            response = raw_response.json()
            if response.get('size', 0) > 0:
                results = response.get('results', [])
                # If parent_id is specified, try to find a page with matching parent
                if parent_id:
                    for page in results:
                        # Get page ancestors to check parent
                        page_id = page['id']
                        page_url = f"https://{organization}.atlassian.net/wiki/rest/api/content/{page_id}?expand=ancestors"
                        page_response = session.get(page_url, headers=headers)
                        if page_response.ok:
                            page_data = page_response.json()
                            ancestors = page_data.get('ancestors', [])
                            if ancestors and ancestors[-1]['id'] == parent_id:
                                return page
                # If no parent specified or no match found, return first result
                return results[0]
            return None
        else:
            logging.warning(f"Could not search for page '{title}': {raw_response.status_code}")
            return None
    except Exception as e:
        logging.error(f"Error searching for page '{title}': {str(e)}")
        return None


def update_confluence_page(organization, space, page_id, user_name, user_credentials, title, content, version=2):
    url = "https://" + organization + ".atlassian.net/wiki/rest/api/content/" + page_id
    data = {
        "id": page_id,
        "title": title,
        "type": "page",
        "space": {
            "key": space
        },
        "status": "current",
        "body": {
            "storage": {
                "value": content,
                "representation": "storage"
            }
        },
        "version": {
            "number": version
        }
    }
    headers = {'Content-Type': 'application/json', 'Accept': 'application/json'}
    session = requests.Session()
    session.auth = (user_name, user_credentials)
    raw_response = session.put(url, data=json.dumps(data), headers=headers)
    if not raw_response.ok:
        logging.error("ERROR from API update request: " + str(raw_response.status_code))
        logging.error("ERROR data: " + str(data))
        logging.error("ERROR response: " + str(raw_response.text))

    response = raw_response.json()
    return response


def update_confluence_page_labels(organization, page_id, user_name, user_credentials, labelsMetadata):
    url = "https://" + organization + ".atlassian.net/wiki/rest/api/content/" + page_id + "/label"
    data = labelsMetadata
    headers = {'Content-Type': 'application/json', 'Accept': 'application/json'}
    session = requests.Session()
    session.auth = (user_name, user_credentials)
    raw_response = session.post(url, data=json.dumps(data), headers=headers)
    if not raw_response.ok:
        logging.error("ERROR from API update request: " + str(raw_response.status_code))
        logging.error("ERROR data: " + str(json.dumps(data)))
        logging.error("ERROR response: " + str(raw_response.text))

    response = raw_response.json()
    return response


def upload_attachment_for_confluence_page(organization, page_id, user_name, user_credentials, file_name, resource_dir):
    url = "https://" + organization + ".atlassian.net/wiki/rest/api/content/" + page_id + "/child/attachment"
    headers = {"X-Atlassian-Token": "nocheck"}
    session = requests.Session()
    session.auth = (user_name, user_credentials)
    response = None
    file_path = resource_dir + "/" + file_name

    try:
        if not Path(file_path).is_file():
            logging.warning(f"File not found: {file_name}")
            return None
    except OSError as e:
        logging.error(f"OSError checking file path for {file_name[:100]}: {str(e)}")
        return None

    with open(file_path, "rb") as f:
        try:
            content_type, encoding = mimetypes.guess_type(file_path)
            if content_type is None:
                content_type = 'multipart/form-data'
            file_data = {'file': (file_name, f, content_type)}
            raw_response = session.post(url, files=file_data, headers=headers)
            if not raw_response.ok:
                if raw_response.status_code == 413:
                    logging.error(f"ERROR: File '{file_name}' is too large to upload (413 - Request Entity Too Large)")
                else:
                    logging.error(f"ERROR from API upload request: {raw_response.status_code} for file '{file_name}'")
                return None
            try:
                response = raw_response.json()
            except ValueError:
                logging.error(f"ERROR: Could not parse JSON response for file '{file_name}'")
                return None
        except yaml.YAMLError as e:
            logging.error(e)
            return None
        except FileNotFoundError as e:
            logging.error(e)
            return None

    return response


def fill_board(confluence_node, board_id, boards_path):
    content = None
    with open(boards_path + "/" + board_id + ".yaml", "r") as f:
        try:
            content = yaml.safe_load(f)
        except yaml.YAMLError as e:
            logging.error(e)

    if 'Items' not in content:
        logging.warning("WARNING no items found for: boardId=" + board_id + ", boardPath=" + boards_path)
        return

    for item in content['Items']:
        if item['Type'] == 'card':
            card = ConfluencePage("not yet available", "not created yet", confluence_node.id, "<h2>placeholder</h2>")
            confluence_node.add_child(card)
            fill_card(card, item['ID'], boards_path + "../cards/")
        elif item['Type'] == 'section':
            section = ConfluencePage(item['Title'], "not created yet", confluence_node.id, "<h2>placeholder</h2>")
            confluence_node.add_child(section)
            if 'Items' not in item:
                logging.warning(
                    "WARNING no items found for section: boardId=" + board_id + ", boardPath=" + boards_path)
                return
            for subitem in item['Items']:
                card = ConfluencePage("not yet available", "not created yet", section.id, "<h2>placeholder</h2>")
                section.add_child(card)
                fill_card(card, subitem['ID'], boards_path + "../cards/")
        else:
            logging.error(
                "ERROR not a CARD/SECTION type: boardId=" + board_id + ', boardPath=' + boards_path + ', item=' + str(
                    item))


def fill_board_group(confluence_node, board_group_id, board_group_path):
    content = None
    with open(board_group_path + "/" + board_group_id + ".yaml", "r") as f:
        try:
            content = yaml.safe_load(f)
        except yaml.YAMLError as e:
            logging.error(e)

    if 'Boards' not in content:
        logging.warning(
            "WARNING no items found for: boardGroupId=" + board_group_id + ", boardGroupPath=" + board_group_path)
        return

    counter = 1
    for itemID in content['Boards']:
        board = ConfluencePage(content['Title'] + "(" + str(counter) + ")", "-1", confluence_node.id,
                               "<h2>" + item['Title'] + "</h2>")
        confluence_node.add_child(board)
        fill_board(board, itemID, board_group_path + "/../boards/")
        counter = counter + 1


def fill_card(confluence_node, card_id, cards_path):
    definition = None
    content = None
    with open(cards_path + "/" + card_id + ".yaml", "r") as f:
        try:
            definition = yaml.safe_load(f)
        except yaml.YAMLError as e:
            logging.error(e)

    with open(cards_path + "/" + card_id + ".html", "r") as f:
        try:
            content = f.read()
        except yaml.YAMLError as e:
            logging.error(e)

    if datedisclaimer == 'yes':
        externalLastUpdated = definition['externalLastUpdated']
        lastUpdatedUTC = datetime.datetime.fromtimestamp(externalLastUpdated / 1000.0, datetime.timezone.utc)
        lastUpdatedDateStr = lastUpdatedUTC.strftime('%Y-%m-%d')
        lastUpdatedTimeStr = lastUpdatedUTC.strftime('%H:%M:%S %Z')
        disclaimer = '<h6><span style="color: rgb(191,38,0);">Imported from Guru. ' \
                     'Original update on <time datetime="{}"/> at {}</span></h6>'.format(lastUpdatedDateStr,
                                                                                         lastUpdatedTimeStr)
        content = disclaimer + content

    try:
        tags = definition['Tags']
    except:
        tags = None

    confluence_node.update_title(definition['Title'])
    confluence_node.update_labels(tags)
    confluence_node.set_content(content)


def create_node(confluence_node, organization, space, user_name, user_credentials, collections_dir):
    # First, check if a page with this title already exists
    existing_page = get_confluence_page_by_title(organization, space, user_name, user_credentials, 
                                                  confluence_node.title, confluence_node.parentId)
    
    if existing_page:
        # Page exists, skip it
        existing_page_id = existing_page['id']
        logging.info(f'SKIPPING EXISTING PAGE "{confluence_node.title}" (ID: {existing_page_id})')
        confluence_node.set_id(existing_page_id)
        
        # Still process children even though we skipped this page
        if len(confluence_node.children) > 0:
            for page in confluence_node.children:
                create_node(page, organization, space, user_name, user_credentials, collections_dir)
        return
    
    # Page doesn't exist, create it
    create_op = create_confluence_page(organization, space, confluence_node.parentId, user_name, user_credentials,
                                       confluence_node.title, confluence_node.htmlContent)
    if 'id' not in create_op:
        new_title = confluence_node.title + " (conflict " + str(randint(1000, 9999)) + ")"
        confluence_node.title = new_title
        create_op = create_confluence_page(organization, space, confluence_node.parentId, user_name, user_credentials,
                                           confluence_node.title, confluence_node.htmlContent)

    new_page_id = create_op['id']
    confluence_node.set_id(new_page_id)
    logging.info('CREATED ' + new_page_id)

    if migratetags == 'yes':
        if confluence_node.labelsMetadata is not None:
            updateLabels = update_confluence_page_labels(organization, new_page_id, user_name, user_credentials,
                                                         confluence_node.labelsMetadata)
            logging.info('UPDATED LABELS ' + new_page_id)
        else:
            logging.info('NO LABELS EXIST ' + new_page_id)

    # upload images
    for image in confluence_node.images:
        result = upload_attachment_for_confluence_page(organization, new_page_id, user_name, user_credentials, image,
                                              collections_dir + '/resources/')
        if result:
            logging.info('IMAGE UPLOADED ' + image)
        else:
            logging.warning('IMAGE UPLOAD FAILED ' + image)

    # update content with image links
    confluence_node.replace_img_with_confluence_image()

    # upload attachments
    for attachment in confluence_node.attachments:
        result = upload_attachment_for_confluence_page(organization, new_page_id, user_name, user_credentials, attachment,
                                              collections_dir + '/resources/')
        if result:
            logging.info('ATTACHMENT UPLOADED ' + attachment)
        else:
            logging.warning('ATTACHMENT UPLOAD FAILED ' + attachment)

    # update content with attachment links
    confluence_node.replace_att_with_confluence_attachment()

    if len(confluence_node.images) > 0 or len(confluence_node.attachments) > 0:
        update_op = update_confluence_page(organization, space, new_page_id, user_name, user_credentials,
                                           confluence_node.title, confluence_node.htmlContent)
        if 'id' not in update_op:
            update_op = update_confluence_page(organization, space, new_page_id, user_name, user_credentials,
                                               confluence_node.title, confluence_node.htmlContent)
        if 'id' in update_op:
            update_page_id = update_op['id']
            logging.info('UPDATED ' + update_page_id)
        else:
            logging.info('UPDATE FAILED ' + new_page_id)
    else:
        logging.info('NO IMAGES or ATTACHMENTS - UPDATE not needed')

    # continue in children
    if len(confluence_node.children) > 0:
        for page in confluence_node.children:
            create_node(page, organization, space, user_name, user_credentials, collections_dir)


def fill_folder(confluence_node, folder_id, folders_path):
    content = None
    with open(folders_path + "/" + folder_id + ".yaml", "r") as f:
        try:
            content = yaml.safe_load(f)
        except yaml.YAMLError as e:
            logging.error(e)

    if not 'Title' in content:
        logging.warning('WARNING no title found for: folderId=' + folder_id + ', folderPath=' + folders_path)
        return
    confluence_node.update_title(content['Title'])

    if 'Description' not in content:
        confluence_node.set_content(content['Title'])
    else:
        confluence_node.set_content(content['Description'])

    if 'Items' not in content:
        logging.warning('WARNING no items found for: folderId=' + folder_id + ', folderPath=' + folders_path)
        return

    for item in content['Items']:
        if item['Type'] == 'card':
            card = ConfluencePage("not yet available", "not created yet", confluence_node.id, "<h2>placeholder</h2>",
                                  item['ID'])
            confluence_node.add_child(card)
            fill_card(card, item['ID'], folders_path + "../cards/")
        elif item['Type'] == 'folder':
            folder = ConfluencePage("unknown", "-1", rootNode.id, "<h2>unknown</h2>", item['ID'])
            confluence_node.add_child(folder)
            fill_folder(folder, item['ID'], folders_path)
        else:
            logging.error(
                'ERROR not a CARD/SECTION type: folderId=' + folder_id + ', folderPath=' + folders_path + ', item=' + str(item))


def initiate_log(quiet):
    currentPath = os.path.dirname(os.path.realpath(__file__))
    scriptName = os.path.basename(__file__).split('.py')[0]
    logFile = currentPath + '/logs/' + scriptName + '_log.log'
    if not os.path.isdir(currentPath + '/logs'):
        os.mkdir(currentPath + '/logs')

    log_handlers =  [logging.FileHandler(logFile)] if quiet else [
            logging.FileHandler(logFile),
            logging.StreamHandler()
        ]
    logging.basicConfig(
        format='[%(asctime)s] %(module)-25s | %(levelname)-8s |  %(message)s',
        datefmt="%Y-%m-%d %H:%M:%S", level=logging.INFO,
        handlers=log_handlers
    )

    logging.info('Starting...')


parser = argparse.ArgumentParser(description='Import Guru collections to Atlassian Confluence.')
parser.add_argument('--collection-dir', dest='collectiondir',
                    help='directory where the collection file is located (default: none)', required=True)
parser.add_argument('--user', dest='username', help='authorized user name (default: none)', required=True)
parser.add_argument('--api-key', dest='apikey', help='the api key for the authorized user (default: none)',
                    required=False)
parser.add_argument('--space-key', dest='spacekey', help='the space key (default: none)', required=True)
parser.add_argument('--organization', dest='org', help='the atlassian organization (default: none)', required=True)
parser.add_argument('--parent', dest='parent', help='the parent page for the import (default: none)', required=True)
parser.add_argument('--date-disclaimer', dest='datedisclaimer', help='[yes|no] add disclaimer and original update '
                                                                     'date on the the top of each card (default: '
                                                                     'none)', required=False)
parser.add_argument('--migrate-tags', dest='migratetags', help='[yes|no] migrate tags (as labels) if were exported',
                    required=False)
parser.add_argument('--quiet', action='store_true', help='No output on stdout',
                    required=False, default=False)

args = parser.parse_args()
seed(datetime.datetime.now().timestamp())

initiate_log(args.quiet)

# Regular expression pattern to find the apikey value
pattern = r"(apikey=')\w+(')"
# Replace the value of apikey with "**********"
sanitized_arguments = re.sub(pattern, r"\1**********\2", 'Arguments {}'.format(args))
logging.info(sanitized_arguments)

if args.datedisclaimer is None:
    datedisclaimer = 'no'
else:
    datedisclaimer = args.datedisclaimer.lower()

if args.migratetags is None:
    migratetags = 'no'
else:
    migratetags = args.migratetags.lower()

rootNode = ConfluencePage("DemoImport", args.parent, "-inf", "<h1>Guru import</h1>",
                          "00000000-0000-0000-0000-000000000000")

content = None

with open(args.collectiondir + "/collection.yaml", "r") as f:
    try:
        content = yaml.safe_load(f)
    except yaml.YAMLError as e:
        logging.error(e)

export_version = 1

if 'Version' in content:
    if content['Version'] == 2:
        export_version = 2

for item in content['Items']:
    # version 1
    if item['Type'] == 'boardgroup' and export_version == 1:
        boardgroup = ConfluencePage(item['Title'], "-1", rootNode.id, "<h2>" + item['Title'] + "</h2>", item['ID'])
        rootNode.add_child(boardgroup)
        fill_board_group(boardgroup, item['ID'], args.collectiondir + "/board-groups/")
    if item['Type'] == 'board' and export_version == 1:
        board = ConfluencePage(item['Title'], "-1", rootNode.id, "<h2>" + item['Title'] + "</h2>", item['ID'])
        rootNode.add_child(board)
        fill_board(board, item['ID'], args.collectiondir + "/boards/")
    if item['Type'] == 'card' and export_version == 1:
        card = ConfluencePage(item['Title'], "-1", rootNode.id, "<h2>" + item['Title'] + "</h2>", item['ID'])
        rootNode.add_child(card)
        fill_card(card, item['ID'], args.collectiondir + "/cards/")
    # version 2
    if item['Type'] == 'folder' and export_version == 2:
        folder = ConfluencePage("unknown", "-1", rootNode.id, "<h2>unknown</h2>", item['ID'])
        rootNode.add_child(folder)
        fill_folder(folder, item['ID'], args.collectiondir + "/folders/")
    if item['Type'] == 'card' and export_version == 2:
        card = ConfluencePage("unknown", "-1", rootNode.id, "<h2>unknown</h2>", item['ID'])
        rootNode.add_child(card)
        fill_card(card, item['ID'], args.collectiondir + "/cards/")
for page in rootNode.children:
    create_node(page, args.org, args.spacekey, args.username, args.apikey, args.collectiondir)
