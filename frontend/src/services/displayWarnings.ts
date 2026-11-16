export function displayWarning(text:string) {
  return text==='NASA WMTS/map registration is unverified; computed map display must remain disabled.'
    ? 'NASA imagery displays the M20 DEM route as a visual demo overlay.' : text;
}
