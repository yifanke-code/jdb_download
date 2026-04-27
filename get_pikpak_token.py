#!/usr/bin/env python3
import asyncio
import json
import sys

from pikpakapi import PikPakApi


async def get_token(username: str, password: str) -> dict | None:
    try:
        client = PikPakApi(username=username, password=password)
        await client.login()
        await client.refresh_access_token()
        return client.get_user_info()
    except Exception as e:
        print(f'Login failed: {e}')
        return None


async def add_magnet(token: str, magnet: str) -> dict | None:
    try:
        client = PikPakApi(encoded_token=token)
        await client.refresh_access_token()
        result = await client.offline_download(file_url=magnet)
        return result
    except Exception as e:
        print(f'Add magnet failed: {e}')
        return None


async def main():
    if len(sys.argv) >= 3:
        username = sys.argv[1]
        password = sys.argv[2]
    else:
        username = input('Email/Phone: ').strip()
        password = input('Password: ').strip()

    print(f'Logging in as {username}...')
    result = await get_token(username, password)
    if result:
        encoded = result.get('encoded_token', '')
        access  = result.get('access_token', '')
        refresh = result.get('refresh_token', '')
        print(f'\nAccess token:  {access[:40]}...')
        print(f'Refresh token: {refresh[:40]}...')
        print(f'\nEncoded token (save this):')
        print(encoded)

        token_data = {
            'encoded_token': encoded,
            'access_token': access,
            'refresh_token': refresh
        }
        with open('pikpak_token.db', 'w') as f:
            json.dump(token_data, f)
        print('\nToken saved to pikpak_token.db')
    else:
        print('Login failed.')


if __name__ == '__main__':
    asyncio.run(main())
