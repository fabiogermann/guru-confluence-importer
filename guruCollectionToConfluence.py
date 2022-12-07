import yaml
import argparse
import json
import requests
import os
import mimetypes

from bs4 import BeautifulSoup

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

class ConfluencePage:
    name_cache = {'root': 1}
    def __init__(self, title, page_id="", parent_id="", html_content=""):
        self.parentId = parent_id
        self.id = page_id
        self.htmlContent = html_content
        self.title = title.encode("ascii", "ignore").decode()
        self.children = []
        self.images = []

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
        title_candidate = title.encode("ascii", "ignore").decode()
        if title_candidate in ConfluencePage.name_cache.keys():
            num_occurence = int(ConfluencePage.name_cache[title_candidate]) + 1
            self.title = title_candidate + " (in multiple boards "+str(num_occurence)+")"
            ConfluencePage.name_cache.update({title_candidate: num_occurence})
        else:
            self.title = title_candidate
            ConfluencePage.name_cache.update({title_candidate: 1})

    def replace_img_with_confluence_image(self):
        soup = BeautifulSoup(self.htmlContent, 'html.parser')
        for img in soup.findAll('img'):
            filename = os.path.basename(img['src'])
            soup_ac_image = BeautifulSoup("<ac:image><ri:attachment ri:filename=\""+filename+"\" /></ac:image>", 'html.parser')
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
    url = "https://"+organization+".atlassian.net/wiki/rest/api/content"
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
    response = session.post(url, data=json.dumps(data), headers=headers).json()
    return response

def update_confluence_page(organization, space, page_id, user_name, user_credentials, title, content, version=2):
    url = "https://"+organization+".atlassian.net/wiki/rest/api/content/"+page_id
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
    response = session.put(url, data=json.dumps(data), headers=headers).json()
    return response

def upload_attachment_for_confluence_page(organization, page_id, user_name, user_credentials, file_name, resource_dir):
    url = "https://"+organization+".atlassian.net/wiki/rest/api/content/"+page_id+"/child/attachment"
    headers = {"X-Atlassian-Token": "nocheck"}
    session = requests.Session()
    session.auth = (user_name, user_credentials)
    response = None
    file_path = resource_dir+"/"+file_name
    with open(file_path, "rb") as f:
        try:
            content_type, encoding = mimetypes.guess_type(file_path)
            if content_type is None:
                content_type = 'multipart/form-data'
            file_data = {'file': (file_name, f, content_type)}
            response = session.post(url, files=file_data, headers=headers).json()
        except yaml.YAMLError as e:
            print(e)

    return response

def fill_board(confluence_node, board_id, boards_path):
    content = None
    with open(boards_path+"/"+board_id+".yaml", "r") as f:
        try:
            content = yaml.safe_load(f)
        except yaml.YAMLError as e:
            print(e)

    for item in content['Items']:
        # print(item)
        if item['Type'] == 'card':
            card = ConfluencePage("not yet available", "not created yet", confluence_node.id, "<h2>placeholder</h2>")
            confluence_node.add_child(card)
            fill_card(card, item['ID'], boards_path+"../cards/")
        else:
            print("ERROR type for: "+item)

def fill_card(confluence_node, card_id, cards_path):
    definition = None
    content = None
    with open(cards_path+"/"+card_id+".yaml", "r") as f:
        try:
            definition = yaml.safe_load(f)
        except yaml.YAMLError as e:
            print(e)

    with open(cards_path+"/"+card_id+".html", "r") as f:
        try:
            content = f.read()
        except yaml.YAMLError as e:
            print(e)

    confluence_node.update_title(definition['Title'])
    confluence_node.set_content(content)

def create_node(confluence_node, organization, space, user_name, user_credentials, collections_dir):
    create_op = create_confluence_page(organization, space, confluence_node.parentId, user_name, user_credentials,
                           confluence_node.title, confluence_node.htmlContent)
    print(create_op)
    new_page_id = create_op['id']
    confluence_node.set_id(new_page_id)
    print("CREATED "+new_page_id)
    # upload images
    for image in confluence_node.images:
        print("UPLOADED "+image)
        upload_attachment_for_confluence_page(organization, new_page_id, user_name, user_credentials, image, collections_dir+"/resources/")
    # update content with image links
    confluence_node.replace_img_with_confluence_image()
    update_op = update_confluence_page(organization, space, new_page_id, user_name, user_credentials,
                           confluence_node.title, confluence_node.htmlContent)
    update_page_id = update_op['id']
    print("UPDATED "+update_page_id)
    # continue in children
    if len(confluence_node.children) > 0:
        for page in confluence_node.children:
            create_node(page, organization, space, user_name, user_credentials, collections_dir)



rootNode = ConfluencePage("DemoImport", args.parent, "-inf", "<h1>Guru import</h1>")

content = None

with open(args.collectiondir+"/collection.yaml", "r") as f:
    try:
        content = yaml.safe_load(f)
    except yaml.YAMLError as e:
        print(e)

for item in content['Items']:
    if item['Type'] == 'board':
        board = ConfluencePage(item['Title'], "-1", rootNode.id, "<h2>"+item['Title']+"</h2>")
        rootNode.add_child(board)
        fill_board(board, item['ID'], args.collectiondir+"/boards/")
    if item['Type'] == 'card':
        card = ConfluencePage(item['Title'], "-1", rootNode.id, "<h2>"+item['Title']+"</h2>")
        rootNode.add_child(card)
        fill_card(card, item['ID'], args.collectiondir+"/cards/")

for page in rootNode.children:
    create_node(page, args.org, args.spacekey, args.username, apikey, args.collectiondir)
