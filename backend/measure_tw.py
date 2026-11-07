import asyncio
from playwright.async_api import async_playwright

async def run():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()
        # Login
        await page.goto('http://127.0.0.1:8000/login/')
        await page.fill('input[name="email"]', 's@gmail.com')
        await page.fill('input[name="password"]', '1234')
        await page.click('button[type="submit"]')
        await page.wait_for_load_state('networkidle')
        
        pages_to_check = ['/', '/charts/', '/history/', '/recurring/', '/groups/']
        for url in pages_to_check:
            await page.goto('http://127.0.0.1:8000' + url, wait_until='networkidle')
            tw_style = await page.evaluate('''() => {
                const styles = Array.from(document.querySelectorAll('style'));
                const tw = styles.find(s => s.textContent.includes('--tw-border-spacing'));
                return tw ? tw.textContent.length : 0;
            }''')
            print(f"Tailwind CSS length on {url}: {tw_style} bytes")
        await browser.close()

asyncio.run(run())
