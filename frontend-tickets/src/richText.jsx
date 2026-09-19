import { Fragment } from 'react'

// Renders the same "markdown-lite" the content/*.md files use (blank line = new
// paragraph, **bold**, *italic*, [text](https://link)) as plain React elements.
// Nothing is ever injected as raw HTML, so content edits can't break the page.
const TOKEN = /\*\*(.+?)\*\*|\*(?!\s)(.+?)(?<!\s)\*|\[([^\]]+)\]\((https?:\/\/[^\s)]+)\)/g

function inline(text, keyPrefix) {
  const nodes = []
  let last = 0
  let i = 0
  for (const m of text.matchAll(TOKEN)) {
    if (m.index > last) nodes.push(text.slice(last, m.index))
    const key = `${keyPrefix}-${i++}`
    if (m[1] !== undefined) nodes.push(<strong key={key}>{m[1]}</strong>)
    else if (m[2] !== undefined) nodes.push(<em key={key}>{m[2]}</em>)
    else nodes.push(<a key={key} href={m[4]} target="_blank" rel="noreferrer">{m[3]}</a>)
    last = m.index + m[0].length
  }
  if (last < text.length) nodes.push(text.slice(last))
  return nodes
}

export default function RichText({ text, className }) {
  const blocks = (text || '').split(/\n\s*\n/).map((b) => b.trim()).filter(Boolean)
  return blocks.map((block, bi) => (
    <p key={bi} className={className}>
      {block.split('\n').map((line, li) => (
        <Fragment key={li}>
          {li > 0 && <br />}
          {inline(line.trim(), `${bi}-${li}`)}
        </Fragment>
      ))}
    </p>
  ))
}
