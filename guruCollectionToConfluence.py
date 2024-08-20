import yaml
import argparse
import json
import requests
import os
import re
import mimetypes
import datetime
import logging

from bs4 import BeautifulSoup
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
            self.images.append(os.path.basename(img['src']))
        for attachment in soup.findAll('a'):
            href = get_element_attribute(attachment, 'href', '')
            if href.startswith('resources/'):
                filename = os.path.basename(href)
                self.attachments.append(filename)
            if 'getguru.com' in href:
                logging.warning('WARNING - Card "{}" contains reference to getguru.com'.format(self.title))
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
        title_candidate = title.replace("&", " and ").encode("ascii", "ignore").decode()
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

    if not Path(file_path).is_file():
        return None

    with open(file_path, "rb") as f:
        try:
            content_type, encoding = mimetypes.guess_type(file_path)
            if content_type is None:
                content_type = 'multipart/form-data'
            file_data = {'file': (file_name, f, content_type)}
            raw_response = session.post(url, files=file_data, headers=headers)
            if not raw_response.ok:
                logging.error("ERROR from API upload request: " + str(raw_response.status_code))
            response = raw_response.json()
        except yaml.YAMLError as e:
            logging.error(e)
        except FileNotFoundError as e:
            logging.error(e)

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
        upload_attachment_for_confluence_page(organization, new_page_id, user_name, user_credentials, image,
                                              collections_dir + '/resources/')
        logging.info('IMAGE UPLOADED ' + image)

    # update content with image links
    confluence_node.replace_img_with_confluence_image()

    # upload attachments
    for attachment in confluence_node.attachments:
        upload_attachment_for_confluence_page(organization, new_page_id, user_name, user_credentials, attachment,
                                              collections_dir + '/resources/')
        logging.info('ATTACHMENT UPLOADED ' + attachment)

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
