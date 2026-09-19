export function normalizeQuantity(value, max=500) {
  const n=Number(value);
  return Number.isFinite(n)?Math.min(max,Math.max(1,Math.trunc(n))):1;
}
export function quote(catalog, value) {
  const product=catalog.products.find(p=>p.id==='PROMPTMASTER_PRO');
  if(!product || catalog.priceBasis!=='gross' || !Number.isSafeInteger(product.monthlyGrossCents) || product.monthlyGrossCents<0 || !Number.isSafeInteger(product.termMonths) || product.termMonths<1 || !Number.isSafeInteger(catalog.taxBasisPoints) || catalog.taxBasisPoints<0 || !Number.isSafeInteger(catalog.maxQuantity) || catalog.maxQuantity<1) throw new Error('Ungültiger Produktkatalog');
  const quantity=normalizeQuantity(value,catalog.maxQuantity);
  const annualUnitGross=product.monthlyGrossCents*product.termMonths;
  const gross=annualUnitGross*quantity;
  if(!Number.isSafeInteger(gross)||!Number.isSafeInteger(gross*10000)) throw new Error('Preis außerhalb des zulässigen Bereichs');
  const net=Math.round(gross*10000/(10000+catalog.taxBasisPoints));
  const tax=gross-net;
  return {quantity,annualUnitGross,net,tax,gross,monthlyGross:product.monthlyGrossCents,termMonths:product.termMonths};
}
export const money=cents=>new Intl.NumberFormat('de-DE',{style:'currency',currency:'EUR'}).format(cents/100);
