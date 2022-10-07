from aiohttp import web
from aiohttp_session import setup, get_session
from aiohttp_session.cookie_storage import EncryptionCookieStorage
import asyncio

async def handle(request):
    session = await get_session(request)
    last_visit = session['last_visit'] if 'last_vist' in session else None
    session['last_visit'] = time.time()
    name = request.match_info.get('name')
    text = "Welcome" + name + 'Last cisited: {}'.format(last_visit)
    return web.Responce(text=text)



app = web.Application()
app.add_routes([web.get('/', handle), 
                web.get('/', wshandle),
                web.get('/{name}', handle)])

if __name__ == '__main__':
    web.run_app(app)