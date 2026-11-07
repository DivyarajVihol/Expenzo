import asyncio
from playwright.async_api import async_playwright

async def run():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()
        
        all_css = set()
        
        # 1. Login & Register
        for url in ['/login/', '/register/']:
            await page.goto('http://127.0.0.1:8000' + url, wait_until='networkidle')
            css = await page.evaluate('''() => {
                const styles = Array.from(document.querySelectorAll('style'));
                const tw = styles.find(s => s.textContent.includes('--tw-border-spacing'));
                return tw ? tw.textContent : '';
            }''')
            if css: all_css.add(css)
            
        # 2. Login
        await page.goto('http://127.0.0.1:8000/login/')
        await page.fill('input[name="email"]', 's@gmail.com')
        await page.fill('input[name="password"]', '1234')
        await page.click('button[type="submit"]')
        await page.wait_for_load_state('networkidle')
        
        for url in ['/', '/charts/', '/history/', '/recurring/', '/groups/', '/streaks/']:
            await page.goto('http://127.0.0.1:8000' + url, wait_until='networkidle')
            css = await page.evaluate('''() => {
                const styles = Array.from(document.querySelectorAll('style'));
                const tw = styles.find(s => s.textContent.includes('--tw-border-spacing'));
                return tw ? tw.textContent : '';
            }''')
            if css: all_css.add(css)
            
        print("Total unique CSS bundles captured:", len(all_css))
        # Merge CSS rules cleanly
        merged_rules = {}
        for bundle in all_css:
            # Simple deduplication by rule
            for rule in bundle.split('}'):
                rule = rule.strip()
                if rule:
                    key = rule.split('{')[0].strip() if '{' in rule else rule
                    merged_rules[key] = rule + '}'
                    
        final_css = '\n'.join(merged_rules.values())
        with open('backend/static/css/tailwind.generated.css', 'w', encoding='utf-8') as f:
            f.write(final_css)
        print("Wrote consolidated tailwind.generated.css, size:", len(final_css), "bytes")
        await browser.close()

asyncio.run(run())
