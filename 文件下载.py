import requests

url = "https://faseb.onlinelibrary.wiley.com/doi/epdf/10.1096/fj.03-0244fje"
headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
}

response = requests.get(url, headers=headers, stream=True)

if response.status_code == 200:
    with open("article.pdf", "wb") as file:
        for chunk in response.iter_content(chunk_size=1024):
            file.write(chunk)
    print("PDF 下载完成: article.pdf")
else:
    print("无法下载 PDF，可能需要登录或其他权限控制。")
