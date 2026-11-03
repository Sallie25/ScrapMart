export function getMaterial(category: string, title = "") {
  const classify = (text: string) => {
    const value = text.toLowerCase();
    if (/cardboard|carton/.test(value)) return "cardboard";
    if (/copper/.test(value)) return "copper";
    if (/alumin[iu]+m/.test(value)) return "aluminium";
    if (/tyre|tire/.test(value)) return "tyres";
    if (/rubber/.test(value)) return "rubber";
    if (/batter/.test(value)) return "batteries";
    if (/motor/.test(value)) return "motor";
    if (/electronic|e-waste/.test(value)) return "electronics";
    if (/engine/.test(value)) return "engine";
    if (/car parts|auto parts/.test(value)) return "engine";
    if (/machinery|mechanical/.test(value)) return "machinery";
    if (/bottle|\bpet\b/.test(value)) return "bottles";
    if (/plastic/.test(value)) return "plastics";
    if (/paper/.test(value)) return "paper";
    if (/iron|steel|ferrous/.test(value)) return "iron";
    if (/metal/.test(value)) return "metal";
    if (/clothes|clothing|textile/.test(value)) return "clothes";
    if (/glass/.test(value)) return "glass";
    return null;
  };
  // Specific listing materials take precedence over broad categories (Metals).
  return classify(title) ?? classify(category) ?? "other";
}
