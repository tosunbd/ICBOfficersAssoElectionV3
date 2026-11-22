/**
 * Election titles are built from two inputs — the council number (e.g. 20)
 * and the year — so the Bengali title is always spelled consistently:
 *   আইসিবি কর্মকর্তা সমিতির ২০তম কার্যনির্বাহী পরিষদ নির্বাচন-২০২৬
 */

/** Council number offered for a new election (the 20th council is elected in 2026). */
export const DEFAULT_COUNCIL_NO = 20;

const BN_DIGITS = "০১২৩৪৫৬৭৮৯";

export function toBengaliDigits(value: number | string): string {
  return String(value).replace(/\d/g, (d) => BN_DIGITS[Number(d)]);
}

function fromBengaliDigits(value: string): string {
  return value.replace(/[০-৯]/g, (d) => String(BN_DIGITS.indexOf(d)));
}

/** ১ম ২য় ৩য় ৪র্থ ৫ম ৬ষ্ঠ ৭ম ৮ম ৯ম ১০ম, then ১১তম, ২০তম … */
export function bengaliOrdinal(n: number): string {
  const suffix: Record<number, string> = { 1: "ম", 2: "য়", 3: "য়", 4: "র্থ", 5: "ম", 6: "ষ্ঠ", 7: "ম", 8: "ম", 9: "ম", 10: "ম" };
  return toBengaliDigits(n) + (suffix[n] ?? "তম");
}

/** 1st 2nd 3rd 4th … 11th 12th 13th … 21st … */
export function englishOrdinal(n: number): string {
  const tens = n % 100;
  if (tens >= 11 && tens <= 13) return `${n}th`;
  return `${n}${({ 1: "st", 2: "nd", 3: "rd" } as Record<number, string>)[n % 10] ?? "th"}`;
}

export function buildTitleBn(councilNo: number, year: number): string {
  return `আইসিবি কর্মকর্তা সমিতির ${bengaliOrdinal(councilNo)} কার্যনির্বাহী পরিষদ নির্বাচন-${toBengaliDigits(year)}`;
}

export function buildTitleEn(councilNo: number, year: number): string {
  return `ICB Officers' Association ${englishOrdinal(councilNo)} Executive Council Election ${year}`;
}

/** Recover the council number from a saved title (Bengali first, then English). */
export function parseCouncilNo(titleBn: string | null | undefined, titleEn?: string | null): number | null {
  const bn = titleBn?.match(/([০-৯]+)(?:তম|ম|য়|য়|র্থ|ষ্ঠ)/);
  if (bn) return Number(fromBengaliDigits(bn[1]));
  const en = titleEn?.match(/(\d+)(?:st|nd|rd|th)\b/i);
  return en ? Number(en[1]) : null;
}
