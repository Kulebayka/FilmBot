import requests

url = "https://api.themoviedb.org/3/movie/550"
params = {"api_key": "331c9a3acfa5effcb6d5d0d0c00c083c"}

response = requests.get(url, params=params)
print(response.status_code)
print(response.text)