// The index is embedded in HTML, so local search works with file:// and without fetch.
const data = JSON.parse(document.getElementById('search-data').textContent);
const input = document.getElementById('book-search');
const results = document.getElementById('search-results');
input.addEventListener('input', () => {
  results.replaceChildren();
  const query = input.value.trim().toLocaleLowerCase();
  if (!query) return;
  let count = 0;
  for (const chapter of data) {
    const position = chapter.text.toLocaleLowerCase().indexOf(query);
    if (position < 0 && !chapter.title.toLocaleLowerCase().includes(query)) continue;
    const li = document.createElement('li');
    const a = document.createElement('a'); a.href = chapter.url; a.textContent = chapter.title;
    const p = document.createElement('p'); p.textContent = chapter.text.slice(Math.max(0, position - 50), Math.max(0, position - 50) + 200);
    li.append(a, p); results.append(li); count++;
    if (count === 30) break;
  }
  if (!count) { const li = document.createElement('li'); li.textContent = 'No matching chapters / 該当する章はありません'; results.append(li); }
});
