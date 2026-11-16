// Presentation names only. API identifiers and stored evidence stay unchanged.
export const DOMAIN_NAMES:Readonly<Record<string,string>>={
  A0:'Mission planning Agent',A1:'Terrain & Traversability',A2:'Thermal Environment',
  A3:'Radiation Exposure',A4:'Geology & Science',A5:'Surface Obstacles',A6:'Rover Operations & Observations',
};
export function domainName(id:string,fallback?:string) {return DOMAIN_NAMES[id] ?? readableText(fallback ?? id);}
export function errorTitle(code:string) {return code.replace(/^A0_/,'PLANNING_').replaceAll('_',' ');}
export function readableText(text:string) {
  return text.replace(/A_STELLAR_A0_MAX_REQUESTS/g,'the local request limit')
    .replace(/A_STELLAR_A0_BUDGET_USD/g,'the local cost limit')
    .replace(/\bA0_[A-Z_]+\b/g,errorTitle)
    .replace(/\bUser-required analyses\b/g,'Required analyses')
    .replace(/\bA[0-6]\b/gi,id=>DOMAIN_NAMES[id.toUpperCase()]);
}
