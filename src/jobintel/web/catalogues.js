// Each catalogue retains one bounded page and cursor identities, never prior bodies.
export class CataloguePages {
  constructor(read){this.read=read;this.entries=new Map();}
  entry(path){if(!this.entries.has(path))this.entries.set(path,{cursors:[null],index:0});return this.entries.get(path);}
  async load(path){const entry=this.entry(path),cursor=entry.cursors[entry.index],query=new URLSearchParams({limit:'20'});if(cursor)query.set('cursor',cursor);return this.read(`${path}${path.includes('?')?'&':'?'}${query}`);}
  move(path,direction,page){const entry=this.entry(path);if(direction==='next'&&page.has_more){entry.cursors[++entry.index]=page.next_cursor;entry.cursors.length=entry.index+1;}else if(direction==='previous'&&entry.index>0)entry.index--;else if(direction==='first'){entry.index=0;entry.cursors=[null];}}
  previous(path){return this.entry(path).index>0;}
  reset(){this.entries.clear();}
}
