const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict'),path=require('node:path');
const root=path.resolve(__dirname,'../dist');
const ids=[...fs.readFileSync(path.join(root,'index.html'),'utf8').matchAll(/id="([^"]+)"/g)].map(m=>m[1]);
const elements=Object.fromEntries(ids.map(id=>[id,{value:'',checked:true,hidden:false,setAttribute(k,v){this[k]=v;},style:{},innerHTML:'',textContent:'',click(){this.onclick();}}]));
Object.assign(elements.level,{value:'grid'});elements.boundaries.value='canton';elements.basemap.value='terrain';
const ctx={scale(){},beginPath(){},moveTo(){},lineTo(){},closePath(){},fill(){}};
const layers=new Set();
const map={createPane(){return {style:{}};},getPane(){return {appendChild(){}};},setView(){return this;},on(){return this;},off(){return this;},getPanes(){return {overlayPane:{appendChild(){}}};},getSize(){return {x:1000,y:700};},getPixelOrigin(){return {x:33000,y:22000};},getZoom(){return 8;},containerPointToLayerPoint(){return {x:0,y:0};},getCenter(){return {lat:46.82,lng:8.23};},project(p,z){const s=256*2**z;const a=Math.sin(p.lat*Math.PI/180);return {x:(p.lng+180)/360*s,y:(.5-Math.log((1+a)/(1-a))/(4*Math.PI))*s};},removeLayer(l){if(layers.has(l)){layers.delete(l);l.onRemove?.(this);}return this;},hasLayer(l){return layers.has(l);},fitBounds(){return this;},attributionControl:{addAttribution(){}}};
const layer=()=>({addTo(){layers.add(this);return this;},on(){return this;},bringToBack(){return this;}});
const L={map:()=>map,latLng:(lat,lng)=>({lat,lng}),control:{zoom:()=>({addTo(){}}),scale:()=>({addTo(){}})},tileLayer:layer,polygon:layer,geoJSON:(data,opts)=>{assert.ok(data.features.length);const l=layer();l.data=data;l.options=opts;return l;},Layer:{extend(def){return class{constructor(){Object.assign(this,def);}addTo(m){layers.add(this);this.onAdd(m);return this;}};}},DomUtil:{create:()=>({style:{},getContext:()=>ctx,remove(){}}),setPosition(){}},DomEvent:{stopPropagation(){}}};
const sandbox={L,window:{addEventListener(){}},document:{getElementById:id=>{assert.ok(elements[id],id);return elements[id];}},proj4:require('../dist/vendor/proj4.js'),Intl,console,devicePixelRatio:1,innerWidth:1000,fetch:async name=>({ok:true,json:async()=>JSON.parse(fs.readFileSync(path.join(root,name),'utf8'))})};
vm.createContext(sandbox);
const code=fs.readFileSync(path.join(root,'app.js'),'utf8').replace(/loadData\(\)\.catch[\s\S]*$/,'');
vm.runInContext(code,sandbox);
(async()=>{
const start=Date.now();await vm.runInContext('loadData()',sandbox);console.log('Full data initialization, mocked map:',Date.now()-start,'ms');
assert.match(elements.status.textContent,/347.*956/);assert.match(elements['source-note'].textContent,/2026-01-01/);
const run=s=>vm.runInContext(s,sandbox);
for(const predicate of ['r=>r[2]===3','r=>r[2]>3&&r[3]===0','r=>r[3]===1']){
run(`{const r=rows.find(${predicate});selectGrid(toLL(r[0]+50,r[1]+50));}`);
assert.match(elements.selection.innerHTML,/residents \/ km²/);
if(predicate.includes('===3'))assert.match(elements.selection.innerHTML,/1–3/);
if(predicate.includes('r[3]===1'))assert.match(elements.selection.innerHTML,/Collective coordinates/);
}
run("selectGrid({lat:0,lng:0})");assert.match(elements.selection.innerHTML,/No published occupied cell/);
run("showRegion(regions.municipality.features.find(f=>!f.properties.population_is_estimate))");assert.match(elements.selection.innerHTML,/official permanent residents/);assert.doesNotMatch(elements.selection.innerHTML,/grid-sum residents/);
run("showRegion(regions.canton.features[0])");assert.match(elements.selection.innerHTML,/Privacy-only count range/);
for(const level of ['municipality','district','canton','grid']){elements.level.value=level;elements.level.onchange();assert.ok(layers.size>=2);}
elements.population.checked=false;elements.population.onchange();assert.equal(run('map.hasLayer(gridLayer)'),false);
elements.boundaries.value='none';elements.boundaries.onchange();assert.equal(layers.size,1);
for(const base of ['topo','aerial','terrain']){elements.basemap.value=base;elements.basemap.onchange();assert.equal(run('map.hasLayer(currentBase)'),true);}
elements['panel-toggle'].onclick();assert.equal(elements['controls-panel'].hidden,true);assert.equal(elements['panel-toggle']['aria-expanded'],'false');
elements['panel-toggle'].onclick();assert.equal(elements['controls-panel'].hidden,false);assert.equal(elements['panel-toggle']['aria-expanded'],'true');
assert.equal(run("escapeHTML('<script>')"),'&lt;script&gt;');
console.log('PASS: real-data schema, transformed grid picking, privacy and NOLOC labels, official/estimate labels, all levels, overlays, base switching. Not browser/render verification.');
})().catch(e=>{console.error(e);process.exitCode=1;});
