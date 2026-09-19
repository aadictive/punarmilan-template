import fs from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'
import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

const here = path.dirname(fileURLToPath(import.meta.url))

// Puts "<Event name> - <Product name>" in the browser tab title. The values
// come from src/chapter.generated.json, which scripts/prepare.py writes.
function chapterTitle() {
  return {
    name: 'chapter-title',
    transformIndexHtml(html) {
      const file = path.join(here, 'src', 'chapter.generated.json')
      if (!fs.existsSync(file)) {
        throw new Error('src/chapter.generated.json is missing - run `python3 scripts/prepare.py` from the repo root first.')
      }
      const c = JSON.parse(fs.readFileSync(file, 'utf8'))
      return html.replace('%PAGE_TITLE%', `${c.event.name} - ${c.chapter_name}`)
    },
  }
}

export default defineConfig({
  plugins: [react(), chapterTitle()],
})
