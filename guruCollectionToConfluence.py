import yaml
import argparse
import json
import requests
import os
import mimetypes

from bs4 import BeautifulSoup
from pathlib import Path
from random import seed
from random import randint

parser = argparse.ArgumentParser(description='Import Guru collections to Atlassian Confluence.')
parser.add_argument('--collection-dir', dest='collectiondir',
                    help='directory where the collection file is located (default: none)', required=True)
parser.add_argument('--user', dest='username', help='sum the integers (default: none)', required=True)
parser.add_argument('--api-key', dest='apikey', help='the api key (default: none)', required=False)
parser.add_argument('--space-key', dest='spacekey', help='the space key (default: none)', required=True)
parser.add_argument('--organization', dest='org', help='the atlassian organization (default: none)', required=True)
parser.add_argument('--parent', dest='parent', help='the parent page for the import (default: none)', required=True)

args = parser.parse_args()
print(args)
seed(1)  # insecure


class ConfluencePage:
    name_cache = {'root': 1}

    def __init__(self, title, page_id="", parent_id="", html_content="", uuid=""):
        self.parentId = parent_id
        self.id = page_id
        self.set_content(html_content)
        self.update_title(title)
        self.children = []
        self.images = []
        self.uuid = uuid

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
        for ruler in soup.findAll('hr'):
            ruler.decompose()
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

    def replace_img_with_confluence_image(self):
        soup = BeautifulSoup(self.htmlContent, 'html.parser')
        for img in soup.findAll('img'):
            filename = os.path.basename(img['src'])
            soup_ac_image = BeautifulSoup("<ac:image><ri:attachment ri:filename=\"" + filename + "\" /></ac:image>",
                                          'html.parser')
            img.replace_with(soup_ac_image)
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
        print("ERROR from API create request: " + str(raw_response.status_code))
        print("ERROR data: " + str(data))
        print("ERROR response: " + str(raw_response.text))
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
        print("ERROR from API update request: " + str(raw_response.status_code))
        print("ERROR data: " + str(data))
        print("ERROR response: " + str(raw_response.text))
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
                print("ERROR from API upload request: " + str(raw_response.status_code))
            response = raw_response.json()
        except yaml.YAMLError as e:
            print(e)
        except FileNotFoundError as e:
            print(e)

    return response


def fill_board(confluence_node, board_id, boards_path):
    content = None
    with open(boards_path + "/" + board_id + ".yaml", "r") as f:
        try:
            content = yaml.safe_load(f)
        except yaml.YAMLError as e:
            print(e)

    if not 'Items' in content:
        print("WARNING no items found for: boardId=" + board_id + ", boardPath=" + boards_path)
        return

    for item in content['Items']:
        if item['Type'] == 'card':
            card = ConfluencePage("not yet available", "not created yet", confluence_node.id, "<h2>placeholder</h2>")
            confluence_node.add_child(card)
            fill_card(card, item['ID'], boards_path + "../cards/")
        elif item['Type'] == 'section':
            section = ConfluencePage(item['Title'], "not created yet", confluence_node.id, "<h2>placeholder</h2>")
            confluence_node.add_child(section)
            if not 'Items' in item:
                print("WARNING no items found for section: boardId=" + board_id + ", boardPath=" + boards_path)
                return
            for subitem in item['Items']:
                card = ConfluencePage("not yet available", "not created yet", section.id, "<h2>placeholder</h2>")
                section.add_child(card)
                fill_card(card, subitem['ID'], boards_path + "../cards/")
        else:
            print("ERROR not a CARD/SECTION type: boardId=" + board_id + ", boardPath=" + boards_path + ", item=" + str(
                item))


def fill_board_group(confluence_node, board_group_id, board_group_path):
    content = None
    with open(board_group_path + "/" + board_group_id + ".yaml", "r") as f:
        try:
            content = yaml.safe_load(f)
        except yaml.YAMLError as e:
            print(e)

    if not 'Boards' in content:
        print("WARNING no items found for: boardGroupId=" + board_group_id + ", boardGroupPath=" + board_group_path)
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
            print(e)

    with open(cards_path + "/" + card_id + ".html", "r") as f:
        try:
            content = f.read()
        except yaml.YAMLError as e:
            print(e)

    confluence_node.update_title(definition['Title'])
    confluence_node.set_content(content)


def create_node(confluence_node, organization, space, user_name, user_credentials, collections_dir):
    create_op = create_confluence_page(organization, space, confluence_node.parentId, user_name, user_credentials,
                                       confluence_node.title, confluence_node.htmlContent)
    if not 'id' in create_op:
        create_op = create_confluence_page(organization, space, confluence_node.parentId, user_name, user_credentials,
                                           confluence_node.title + " (conflict " + str(randint(111, 222)) + ")",
                                           confluence_node.htmlContent)
    new_page_id = create_op['id']
    confluence_node.set_id(new_page_id)
    print("CREATED " + new_page_id)
    # upload images
    for image in confluence_node.images:
        print("UPLOADED " + image)
        upload_attachment_for_confluence_page(organization, new_page_id, user_name, user_credentials, image,
                                              collections_dir + "/resources/")
    # update content with image links
    confluence_node.replace_img_with_confluence_image()
    if len(confluence_node.images) > 0:
        update_op = update_confluence_page(organization, space, new_page_id, user_name, user_credentials,
                                           confluence_node.title, confluence_node.htmlContent)
        if not 'id' in update_op:
            update_op = update_confluence_page(organization, space, new_page_id, user_name, user_credentials,
                                               confluence_node.title, confluence_node.htmlContent)
        if 'id' in update_op:
            update_page_id = update_op['id']
            print("UPDATED " + update_page_id)
        else:
            print("UPDATED FAILED" + new_page_id)
    else:
        print("UPDATED not needed")
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
            print(e)

    if not 'Title' in content:
        print("WARNING no title found for: folderId=" + folder_id + ", folderPath=" + folders_path)
        return
    confluence_node.update_title(content['Title'])

    if not 'Description' in content:
        confluence_node.set_content(content['Title'])
    else:
        confluence_node.set_content(content['Description'])

    if not 'Items' in content:
        print("WARNING no items found for: folderId=" + folder_id + ", folderPath=" + folders_path)
        return

    for item in content['Items']:
        if item['Type'] == 'card':
            card = ConfluencePage("not yet available", "not created yet", confluence_node.id, "<h2>placeholder</h2>", item['ID'])
            confluence_node.add_child(card)
            fill_card(card, item['ID'], folders_path + "../cards/")
        elif item['Type'] == 'folder':
            folder = ConfluencePage("unknown", "-1", rootNode.id, "<h2>unknown</h2>", item['ID'])
            confluence_node.add_child(folder)
            fill_folder(folder, item['ID'], folders_path)
        else:
            print(
                "ERROR not a CARD/SECTION type: folderId=" + folder_id + ", folderPath=" + folders_path + ", item=" + str(
                    item))


rootNode = ConfluencePage("DemoImport", args.parent, "-inf", "<h1>Guru import</h1>", "00000000-0000-0000-0000-000000000000")

content = None

with open(args.collectiondir + "/collection.yaml", "r") as f:
    try:
        content = yaml.safe_load(f)
    except yaml.YAMLError as e:
        print(e)

export_version = 1

if "Version" in content:
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
for page in rootNode.children:
    create_node(page, args.org, args.spacekey, args.username, args.apikey, args.collectiondir)
