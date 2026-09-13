import {readFile,writeFile,mkdir} from 'node:fs/promises';
import {renderContent,footer} from '../src/content.js';
let html=await readFile('dist/index.html','utf8');
html=html.replace('<div id="content"></div>','<div id="content">'+renderContent()+'</div>').replace('<footer id="footer"></footer>','<footer id="footer">'+footer()+'</footer>');
html=html.replace('</head>','<meta name="robots" content="noindex, nofollow"></head>');
html=html.replace('</body>','<noscript><p class="notice">Für den Preisrechner und den interaktiven Kopf aktiviere bitte JavaScript.</p></noscript></body>');
await writeFile('dist/index.html',html);
const routes=['free','pro','preise','vergleich','checkout','login','portal','app/pro','impressum','datenschutz','lizenzbedingungen','agb','kontakt','unternehmen'];
for(const route of routes){
  await mkdir('dist/'+route,{recursive:true});
  let routeHtml=html;
  if(!['pro','preise','vergleich'].includes(route)){
    routeHtml=routeHtml.replace(/<main id="main">[\s\S]*?<\/main>/,'<main id="main"><section class="route-page"><h1>PromptMaster · Vorschau</h1><p>Diese Funktion ist noch nicht freigeschaltet. Für weitere Informationen aktiviere bitte JavaScript.</p><a class="button secondary" href="/">Zur Startseite →</a></section></main>');
  }
  await writeFile('dist/'+route+'/index.html',routeHtml);
}
await writeFile('dist/404.html',html.replace(/<main id="main">[\s\S]*?<\/main>/,'<main id="main"><section class="route-page"><h1>Diese Seite gibt es nicht.</h1><a href="/">Zur Startseite</a></section></main>'));
console.log('14 vorbereitete Routen und statische Marketing-Inhalte erstellt.');
