from fastapi import FastAPI, Request, HTTPException, status
from bs4 import BeautifulSoup
import aiohttp
import aiofiles
import asyncio
import json
import os
import uvicorn

app = FastAPI()

# Путь к файлу базы данных
DB_FILE_PATH = "data/whitelist.json"


def create_file_database(filename: str, path="data"):
    os.makedirs(path, exist_ok=True)
    if not os.path.exists(f"{path}/{filename}.json"):
        print("[!] Инициализация простенькой базы данных")
        with open(f"{path}/{filename}.json", "w", encoding="utf-8") as file:
            data = {"whitelisted_ips": []}
            json_res = json.dumps(data, indent=4, ensure_ascii=False)
            file.write(json_res)


async def add_new_ip(ip: str, response_count: int):
    data = await read_data_base(DB_FILE_PATH)
    whitelisted_ips = data["whitelisted_ips"]
    if ip not in [i["ip"] for i in whitelisted_ips]:
        whitelisted_ips.append({
            "ip": ip,
            "max_response_count": response_count,
            "response_count": 0
        })
        await update_data_base(DB_FILE_PATH, data)


async def remove_ip(ip: str):
    data = await read_data_base(DB_FILE_PATH)
    whitelisted_ips = data["whitelisted_ips"]
    whitelisted_ips = [i for i in whitelisted_ips if i["ip"] != ip]
    data["whitelisted_ips"] = whitelisted_ips
    await update_data_base(DB_FILE_PATH, data)


async def read_data_base(file_path):
    async with aiofiles.open(file_path, mode='r', encoding='utf-8') as file:
        contents = await file.read()
        data = json.loads(contents)
        return data


async def update_data_base(file_path, data):
    async with aiofiles.open(file_path, mode='w', encoding='utf-8') as file:
        contents = json.dumps(data, indent=4, ensure_ascii=False)
        await file.write(contents)


async def get_root_response():
    secret_domain = "http://185.25.48.97:64993/by_ip/proxy_list"
    async with aiohttp.ClientSession() as session:
        async with session.get(url=secret_domain) as resp:
            soup = BeautifulSoup(await resp.text(), "html.parser")
            return soup.text


@app.get("/api/proxies/list")
async def get_proxies(request: Request):
    client_ip = request.client.host
    whitelist = await read_data_base(DB_FILE_PATH)
    client_ip = str(client_ip).split(":")[0]
    if client_ip not in [i["ip"] for i in whitelist["whitelisted_ips"]]:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=f"IP address not allowed: {client_ip}")

    current_ip_data = next((i for i in whitelist["whitelisted_ips"] if i["ip"] == client_ip), None)
    max_response = current_ip_data["max_response_count"]
    current_response = current_ip_data["response_count"] + 1
    if current_response > max_response:
        raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail=f"Too many requests per ip: {client_ip}")

    # Обновление счетчика запросов
    current_ip_data["response_count"] = current_response

    # Обновление данных в whitelist
    for entry in whitelist["whitelisted_ips"]:
        if entry["ip"] == client_ip:
            entry.update(current_ip_data)
            break

    await update_data_base(DB_FILE_PATH, whitelist)
    proxies = await get_root_response()
    return proxies.replace("\r\n", " ")


async def command_listener():
    await asyncio.sleep(3)
    while True:
        try:
            user_input = input("➝ Введите команду (help для помощи): ")
            combo = user_input.split()
            command = combo[0]
        except Exception:
            continue
        if command == "help":
            print("", "↪ add [ip-адрес] [количество запросов] -> Добавить айпи адрес в вайт лист",
                  "↪ remove [ip-адрес] -> Удалить айпи из вайт листа", "", sep="\n", )
        elif command == "add":
            if len(combo) < 3:
                continue
            ip, response_count = combo[1], int(combo[2])
            await add_new_ip(ip, response_count)
            print(f"[!]: Успешно ip: {ip} с количеством запросов: {response_count} добавлен")
        elif command == "remove":
            if len(combo) < 2:
                continue
            ip = combo[1]
            await remove_ip(ip)
            print(f"[!]: Успешно ip: {ip} удален")
        else:
            print("[X] Неизвестная команда")
        await asyncio.sleep(1)  # небольшой перерыв перед следующим запросом


def start_command_listener():
    asyncio.run(command_listener())


if __name__ == "__main__":
    create_file_database("whitelist", "data")

    # Запуск командного слушателя в отдельном потоке
    import threading
    command_thread = threading.Thread(target=start_command_listener)
    command_thread.start()

    # Запуск приложения FastAPI
    print("➤ Запускаю работу программы")
    uvicorn.run(app, host="0.0.0.0", port=8000)
