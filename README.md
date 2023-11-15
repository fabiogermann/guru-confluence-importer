# guru-confluence-importer

Easily import Guru collections to Confluence.

Currently tested with: 
 * `https://app.getguru.com/` exported collection as ZIP
 * `https://?????.atlassian.net/wiki` Atlassian Confluence Cloud

## Usage

```
python3 guruCollectionToConfluence.py \
  --collection-dir ../export-20221201010000-/ \
  --user <user@org.com> \
  --api-key <apikey>
  --space-key '~PRIVATESPACE' \
  --parent 999999 \
  --organization myorg
```

* `--collection-dir`: path to the extracted guru collection
* `--user`: email address that is associated with the API key
* `--api-key`: API key associated with the user (https://id.atlassian.com/manage-profile/security/api-tokens)
* `--space-key`: Confluence space that will contain the imported collection (see below "obtaining space key")
* `--parent`: page ID that should contain the imported collections (see below "obtaining parent page id")
* `--organization`: the subdomain part / name of the organization (i.e. "bestcorp" if the Confluence url is "bestcorp.atlassian.net")


### Obtaining the space key
![Screenshot 2022-12-07 at 13 50 00](https://user-images.githubusercontent.com/2370607/206270068-dcec91ad-2cbe-4d82-9501-35817539e140.png)

### Obtaining the parent page id
![Screenshot 2022-12-07 at 13 55 53](https://user-images.githubusercontent.com/2370607/206271427-02cbbf6f-7399-408e-b188-b84e5b4adf71.png)
![Screenshot 2022-12-07 at 13 56 29](https://user-images.githubusercontent.com/2370607/206271447-9dcd8f94-7ee7-4268-a006-c496ada6c24b.png)

## References
[Atlassian Forum Mention 1](https://community.atlassian.com/t5/Confluence-questions/How-to-import-from-guru-cards-to-confluence-pages/qaq-p/2031581#M285446)
