/* Official data schema is normalized in loadData below. */
'use strict';
const $ = id => document.getElementById(id);
const fmt = n => new Intl.NumberFormat('en-CH',{maximumFractionDigits:1}).format(n);
const escapeHTML = s => String(s).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const projection = '+proj=somerc +lat_0=46.95240555555556 +lon_0=7.439583333333333 +k_0=1 +x_0=600000 +y_0=200000 +ellps=bessel +towgs84=674.374,15.056,405.346,0,0,0,0 +units=m +no_defs';
const swissTransform=proj4(projection,'EPSG:4326');
const toLL = (x,y) => {const p=swissTransform.forward([x,y]);return L.latLng(p[1],p[0]);};
const map = L.map('map',{zoomControl:false,preferCanvas:true,minZoom:7,maxZoom:19}).setView([46.82,8.23],8);
map.createPane('population').style.zIndex=350;
L.control.zoom({position:'topright'}).addTo(map);
L.control.scale({position:'bottomright',imperial:false}).addTo(map);
const attribution='<a href="https://www.swisstopo.admin.ch/">© swisstopo</a>';
const tile = (id,ext) => L.tileLayer(`https://wmts.geo.admin.ch/1.0.0/${id}/default/current/3857/{z}/{x}/{y}.${ext}`,{attribution,maxZoom:19,maxNativeZoom:18});
const bases={terrain:tile('ch.swisstopo.swissalti3d-reliefschattierung','png'),topo:tile('ch.swisstopo.pixelkarte-farbe','jpeg'),aerial:tile('ch.swisstopo.swissimage','jpeg')};
let currentBase=bases.terrain.addTo(map), failedTiles=0;
Object.values(bases).forEach(b=>b.on('tileerror',()=>{if(++failedTiles>2)$('status').textContent='Some base-map tiles could not load. Try another base map.';}));
map.attributionControl.addAttribution('<a href="https://statistik.admin.ch/">© FSO · STATPOP</a>');
const colors=['#440154','#3b528b','#21918c','#5ec962','#fde725'];
let rows=[],regions={},gridIndex=new Map(),worldCells,regionLayer,boundaryLayer,selectedCell;
function breaks(){return $('level').value==='grid'?[0,1000,5000,10000,25000]:[0,50,200,500,1000];}
function color(d){const b=breaks();let i=0;while(i<4&&d>=b[i+1])i++;return colors[i];}
const GridCanvas=L.Layer.extend({
 onAdd(m){this.canvas=L.DomUtil.create('canvas','population-canvas leaflet-zoom-hide');m.getPane('population').appendChild(this.canvas);m.on('moveend zoomend resize',this.draw,this);this.draw();},
 onRemove(m){m.off('moveend zoomend resize',this.draw,this);this.canvas.remove();},
 draw(){if(!this.canvas||!worldCells)return;const size=map.getSize(),origin=map.getPixelOrigin(),scale=2**map.getZoom(),top=map.containerPointToLayerPoint([0,0]),ratio=devicePixelRatio||1;
 L.DomUtil.setPosition(this.canvas,top);this.canvas.width=size.x*ratio;this.canvas.height=size.y*ratio;this.canvas.style.width=size.x+'px';this.canvas.style.height=size.y+'px';const ctx=this.canvas.getContext('2d');ctx.scale(ratio,ratio);ctx.globalAlpha=.76;
 const ox=origin.x+top.x,oy=origin.y+top.y;
 for(let i=0;i<rows.length;i++){const k=i*8,x=worldCells[k]*scale-ox,y=worldCells[k+1]*scale-oy,x2=worldCells[k+4]*scale-ox,y2=worldCells[k+5]*scale-oy;if(Math.max(x,x2)<0||Math.min(x,x2)>size.x||Math.max(y,y2)<0||Math.min(y,y2)>size.y)continue;
 ctx.fillStyle=color(rows[i][2]*100);ctx.beginPath();ctx.moveTo(x,y);for(let j=2;j<8;j+=2)ctx.lineTo(worldCells[k+j]*scale-ox,worldCells[k+j+1]*scale-oy);ctx.closePath();ctx.fill();}
 }
});
const gridLayer=new GridCanvas();
function selectGrid(latlng){if($('level').value!=='grid'||!$('population').checked)return;const p=swissTransform.inverse([latlng.lng,latlng.lat]),bx=Math.floor(p[0]/100),by=Math.floor(p[1]/100);let r;
 for(let dx=-1;dx<=1;dx++)for(let dy=-1;dy<=1;dy++){const candidates=gridIndex.get((bx+dx)+','+(by+dy))||[];for(const candidate of candidates){if(p[0]>=candidate[0]&&p[0]<candidate[0]+100&&p[1]>=candidate[1]&&p[1]<candidate[1]+100)r=candidate;}}
 if(selectedCell)map.removeLayer(selectedCell);if(!r){$('selection').innerHTML='<h2>No published occupied cell</h2><p>This location has no occupied cell in the published grid, or lies outside coverage.</p>';return;}
 const x=r[0],y=r[1],n=r[2],small=n===3,label=small?'1–3':fmt(n),density=small?'100–300':fmt(n*100);
 selectedCell=L.polygon([[x,y],[x+100,y],[x+100,y+100],[x,y+100]].map(p=>toLL(...p)),{color:'#111',weight:2,fill:false,interactive:false}).addTo(map);
 $('selection').innerHTML=`<h2>100 × 100 m cell</h2><div class="value">${density} <span class="unit">residents / km²</span></div><div class="stats"><div><strong>${label}</strong><span>permanent residents</span></div><div><strong>0.01 km²</strong><span>cell area</span></div></div><p>LV03 southwest: ${x}, ${y}.${small?' Privacy-grouped count.':''}</p>${r[3]?'<p><strong>Collective coordinates:</strong> includes residents whose precise address is unavailable; this may not be their residential location.</p>':''}`;
}
map.on('click',e=>selectGrid(e.latlng));
function showRegion(f){const p=f.properties,estimated=p.population_is_estimate;
 const label=estimated?'grid-sum residents ≈':'official permanent residents';
 const note=estimated?'Estimate: privacy-grouped cells assigned by southwest corner. Privacy-only count range: '+fmt(p.grid_population_lower)+'–'+fmt(p.grid_population_upper)+'. Spatial allocation error is additional.':'Official 2025 municipality count; density calculated using 2026 boundary area.';
 $('selection').innerHTML=`<h2>${escapeHTML(p.name)}</h2><div class="value">${fmt(p.density_per_km2)} <span class="unit">residents / km²${estimated?' ≈':''}</span></div><div class="stats"><div><strong>${fmt(p.population)}</strong><span>${label}</span></div><div><strong>${fmt(p.area_km2)} km²</strong><span>total polygon area</span></div></div><p>${note}</p>`;
}
function render(){if(!rows.length)return;if(regionLayer)map.removeLayer(regionLayer);if(boundaryLayer)map.removeLayer(boundaryLayer);if(map.hasLayer(gridLayer))map.removeLayer(gridLayer);if(selectedCell){map.removeLayer(selectedCell);selectedCell=null;}
 const level=$('level').value;
 if($('population').checked){if(level==='grid')gridLayer.addTo(map);else regionLayer=L.geoJSON(regions[level],{style:f=>({fillColor:color(f.properties.density_per_km2),fillOpacity:.66,color:'#465b66',weight:.7}),onEachFeature:(f,l)=>l.on('click',e=>{L.DomEvent.stopPropagation(e);showRegion(f);})}).addTo(map);}
 const boundary=$('boundaries').value;if(boundary!=='none')boundaryLayer=L.geoJSON(regions[boundary],{interactive:false,style:{color:'#344751',weight:boundary==='canton'?1.4:.65,opacity:.7,fill:false}}).addTo(map);
 $('ticks').innerHTML=breaks().map(n=>`<span>${fmt(n)}${n===breaks()[4]?'+':''}</span>`).join('');
 $('ramp').style.background=`linear-gradient(to right,${colors.flatMap((c,i)=>[c+' '+i*20+'%',c+' '+(i+1)*20+'%']).join(',')})`;
 $('legend-note').textContent=level==='grid'?'100 × 100 m cells. Uncoloured: no published occupied cell.':'Official municipality totals where matched; other regions use grid estimates. Districts do not cover all cantons.';
 $('selection').innerHTML='<h2>Explore the map</h2><p>Click '+(level==='grid'?'a populated cell':'an administrative area')+' to see its values.</p>';
}
$('level').onchange=render;$('boundaries').onchange=render;$('population').onchange=render;
$('basemap').onchange=()=>{map.removeLayer(currentBase);currentBase=bases[$('basemap').value].addTo(map);currentBase.bringToBack();failedTiles=0;};
$('reset').onclick=()=>map.fitBounds([[45.82,5.96],[47.81,10.49]],{paddingTopLeft:[innerWidth>640?310:230,20],paddingBottomRight:[20,20]});
async function fetchJSON(path){const r=await fetch(path);if(!r.ok)throw new Error(path+' returned '+r.status);return r.json();}
async function loadData(){
 // Schema adapter completed against generated official data artifacts.
 const data=await fetchJSON('data/grid.json');rows=data.cells;
 const names={municipality:'municipalities',district:'districts',canton:'cantons'};await Promise.all(Object.entries(names).map(async ([n,file])=>{regions[n]=await fetchJSON('data/'+file+'.geojson');}));const metadata=await fetchJSON('data/metadata.json');
 worldCells=new Float64Array(rows.length*8);
 rows.forEach((r,i)=>{const key=Math.floor(r[0]/100)+','+Math.floor(r[1]/100);if(!gridIndex.has(key))gridIndex.set(key,[]);gridIndex.get(key).push(r);[[r[0],r[1]],[r[0]+100,r[1]],[r[0]+100,r[1]+100],[r[0],r[1]+100]].forEach((c,j)=>{const p=map.project(toLL(...c),0);worldCells[i*8+j*2]=p.x;worldCells[i*8+j*2+1]=p.y;});});
 $('vintage').textContent='STATPOP 2025 · 100 m grid';$('source-note').textContent='Population: '+metadata.population_date.slice(0,10)+'. Boundaries: '+metadata.boundary_date.slice(0,10)+'. The 100 m grid is the finest published STATPOP resolution. Cells with collective coordinates may include residents without a precise address. Display boundaries simplified by 20 m.';
 $('status').textContent=fmt(rows.length)+' published occupied cells · click to inspect';render();$('reset').click();
}
$('inspect').onclick=()=>{if($('level').value==='grid')selectGrid(map.getCenter());};
loadData().catch(e=>{$('status').textContent='Data could not load. Reload the page to try again.';console.error(e);});
