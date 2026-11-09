// Playwright MCP browser_run_code_unsafe filename; open the local app first.
async (page) => {
 const results = [];
 await page.waitForFunction(() => typeof worldCells !== 'undefined' && worldCells && document.getElementById('status').textContent.includes('published occupied cells'));
 async function clickMapCentre() {
  const p = await page.evaluate(() => {const b = document.getElementById('map').getBoundingClientRect(); return {x:b.x+b.width/2,y:b.y+b.height/2};});
  await page.mouse.click(p.x,p.y);
 }
 for (const size of [{width:1200,height:762},{width:390,height:844},{width:320,height:568},{width:640,height:360}]) {
  await page.setViewportSize(size);
  await page.locator('#reset').click();
  await page.waitForFunction(() => !map._animatingZoom);
  const good = await page.evaluate(() => {
   const m = document.getElementById('map').getBoundingClientRect(),a = document.querySelector('aside').getBoundingClientRect();
   const points = [[45.82,5.96],[47.81,10.49]].map(ll => map.latLngToContainerPoint(ll));
   return document.documentElement.scrollWidth <= innerWidth && points.every(p => p.x >= 0 && p.x <= m.width && p.y >= 0 && p.y <= m.height) && (innerWidth > 640 || a.top >= m.bottom - 1);
  });
  if (!good) throw Error('Map fit/layout failed: '+JSON.stringify(size));
  results.push({viewport:size,fit:true});
 }
 await page.setViewportSize({width:1200,height:762});
 await page.locator('#level').selectOption('grid');
 await page.locator('#population').setChecked(true);
 for (const kind of ['exact','privacy','collective']) {
  const expected = await page.evaluate(kind => {
   const r = rows.find(r => kind === 'privacy' ? r[2] === 3 : kind === 'collective' ? r[3] === 1 : r[2] > 3 && !r[3]);
   map.setView(toLL(r[0]+50,r[1]+50),16,{animate:false});
   return {population:r[2],density:r[2]*100};
  },kind);
  await clickMapCentre();
  const text = await page.locator('#selection').innerText();
  if (!text.includes('100 × 100 m cell')) throw Error(kind+' click failed');
  if (kind === 'privacy' && (!text.includes('1–3') || !text.includes('100–300'))) throw Error('Privacy grouping incorrect');
  if (kind === 'collective' && !text.includes('Collective coordinates:')) throw Error('Collective warning missing');
  if (kind === 'exact' && !text.includes(new Intl.NumberFormat('en-CH').format(expected.density))) throw Error('Density mismatch');
  results.push({cell:kind,...expected});
 }
 const z = await page.evaluate(() => map.getZoom());
 await page.getByRole('button',{name:'Zoom in',exact:true}).click();
 await page.waitForFunction(z => map.getZoom() === z+1 && !map._animatingZoom,z);
 await page.getByRole('button',{name:'Zoom out',exact:true}).click();
 await page.waitForFunction(z => map.getZoom() === z && !map._animatingZoom,z);
 await page.getByRole('button',{name:'Inspect map centre (grid)',exact:true}).click();
 if (!(await page.locator('#selection').innerText()).includes('100 × 100 m cell')) throw Error('Centre inspector failed');
 const before = await page.evaluate(() => map.getCenter());
 await page.locator('#map').focus();await page.keyboard.press('ArrowRight');
 await page.waitForFunction(before => map.getCenter().lng !== before.lng,before);
 // Actual pointer drag, not a programmatic pan.
 const centre = await page.locator('#map').boundingBox();
 const prior = await page.evaluate(() => map.getCenter().lng);
 await page.mouse.move(centre.x+centre.width*.65,centre.y+centre.height*.4);await page.mouse.down();
 await page.mouse.move(centre.x+centre.width*.65+80,centre.y+centre.height*.4+30,{steps:6});await page.mouse.up();
 await page.waitForFunction(prior => map.getCenter().lng !== prior,prior);
 for (const level of ['municipality','district','canton']) {
  await page.locator('#level').selectOption(level);
  await page.evaluate(() => {map.setView([47.3769,8.5417],11,{animate:false});});
  await clickMapCentre();
  const text = await page.locator('#selection').innerText();
  const expected = await page.evaluate(level => regions[level].features.find(f => f.properties.name === document.querySelector('#selection h2').textContent)?.properties,level);
  if (!expected) throw Error(level+' click failed');
  if (!text.includes(new Intl.NumberFormat('en-CH',{maximumFractionDigits:1}).format(expected.density_per_km2)) || !text.includes(expected.population_is_estimate ? 'grid-sum residents' : 'official permanent residents')) throw Error('Regional value/source mismatch');
  results.push({level,name:expected.name,population:expected.population,density:expected.density_per_km2,estimate:expected.population_is_estimate});
 }
 let combinations = 0;
 for (const level of ['grid','municipality','district','canton']) {
  await page.locator('#level').selectOption(level);
  for (const boundary of ['none','municipality','district','canton']) {
   await page.locator('#boundaries').selectOption(boundary);
   for (const visible of [false,true]) {
    await page.locator('#population').setChecked(visible);
    const good = await page.evaluate(({level,boundary,visible}) => (level === 'grid' ? map.hasLayer(gridLayer) : map.hasLayer(regionLayer)) === visible && Boolean(boundaryLayer && map.hasLayer(boundaryLayer)) === (boundary !== 'none'),{level,boundary,visible});
    if (!good) throw Error('Layer combination failed');
    combinations++;
   }
  }
 }
 for (const base of ['topo','aerial','terrain']) {
  await page.locator('#basemap').selectOption(base);
  await page.waitForFunction(() => Object.values(currentBase._tiles).some(t => t.el.complete && t.el.naturalWidth > 0));
 }
 // Fault injection at the tile event boundary: inactive sources cannot overwrite status.
 const statuses = await page.evaluate(() => {
  const inactive = Object.values(bases).find(b => b !== currentBase);
  for(let i=0;i<3;i++) inactive.fire('tileerror');
  const inactiveIgnored = document.getElementById('status').textContent === dataStatus;
  currentBase.fire('loading');for(let i=0;i<3;i++) currentBase.fire('tileerror');
  const warned = document.getElementById('status').textContent.includes('could not load');
  currentBase.fire('loading');currentBase.fire('load');
  return {inactiveIgnored,warned,recovered:document.getElementById('status').textContent === dataStatus};
 });
 if (!Object.values(statuses).every(Boolean)) throw Error('Tile status handling failed');
 await page.getByText('Data & precision',{exact:true}).click();
 const detail = await page.locator('details').innerText();
 if (!detail.includes('2025-12-31') || !detail.includes('2026-01-01')) throw Error('Source dates missing');
 await page.getByText('Data & precision',{exact:true}).click();
 await page.setViewportSize({width:390,height:844});
 await page.locator('#level').selectOption('grid');
 await page.evaluate(() => {const r=rows.find(r => r[2] === 3);map.setView(toLL(r[0]+50,r[1]+50),16,{animate:false});});
 await clickMapCentre();
 const revealed = await page.evaluate(() => {const s=document.getElementById('selection').getBoundingClientRect(),a=document.querySelector('aside').getBoundingClientRect();return s.top >= a.top-1 && s.bottom <= a.bottom+1;});
 if (!revealed) throw Error('Mobile selected values hidden');
 await page.setViewportSize({width:1200,height:762});await page.locator('#boundaries').selectOption('canton');await page.locator('#reset').click();
 return {results,layerCombinations:combinations,bases:3,pointerDrag:true,keyboardPan:true,zoomButtons:true,centreInspector:true,mobileSelectionRevealed:true,tileStatus:statuses};
}
