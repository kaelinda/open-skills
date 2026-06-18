# MDNice API Notes

These notes describe the MDNice endpoints used by `scripts/md_to_html.py`.

## Theme List

Endpoint:

```http
GET https://api.mdnice.com/themes?pageSize=100&currentPage=1
```

Authentication is not required for public theme metadata. The response shape is:

```json
{
  "success": true,
  "code": 0,
  "message": "操作成功！",
  "data": {
    "themeList": [
      {
        "themeId": 3060,
        "name": "重影",
        "cover": "https://files.mdnice.com/...",
        "writingOutId": "...",
        "applicantUsername": "...",
        "description": "...",
        "isPublic": true,
        "css": null
      }
    ],
    "pageNum": 30
  }
}
```

`pageNum` behaves like the total available theme count in current responses, not the number of pages.

## Theme Style

Endpoint:

```http
PUT https://api.mdnice.com/articles/styles
Content-Type: application/json;charset=UTF-8
Authorization: Bearer <MDNICE_TOKEN>

{"outId":"<MDNICE_OUT_ID>","themeId":13}
```

Authentication is required. Without a bearer token the API returns:

```json
{"code":20001,"message":"用户未登录，请先登录","success":false}
```

The response contains `data.style`, a CSS string targeting `#nice`, plus `data.styleModelList` and `data.dataVersion`. The script stores only the CSS and small metadata in `references/mdnice-themes.json`.

Because the endpoint is a `PUT` under an article path, treat style refreshes as potentially mutating the MDNice article identified by `outId`. Use a disposable article when fetching or refreshing styles.

## Credentials

Use environment variables instead of command-line tokens:

```bash
export MDNICE_TOKEN="..."
export MDNICE_OUT_ID="..."
```

Do not commit bearer tokens or personal article IDs into the skill.
