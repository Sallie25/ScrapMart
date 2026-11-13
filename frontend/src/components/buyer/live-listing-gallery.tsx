"use client";
import { useState } from "react";
import Image from "next/image";
import type { CatalogueListing } from "@/lib/marketplace/catalogue";

export function LiveListingGallery({ listing }: { listing: CatalogueListing }) {
  const photos = [...listing.photos].sort((a, b) => a.position - b.position);
  const [selected, setSelected] = useState(0);
  const active = photos[selected];
  return <div className="min-w-0"><div className="overflow-hidden rounded-3xl"><Image unoptimized src={active.url} alt={`${listing.title}, photo ${selected + 1}`} width={active.width ?? 800} height={active.height ?? 600} className="aspect-[4/3] w-full object-cover" /></div>
    {photos.length > 1 && <div className="mt-3 flex flex-wrap gap-3" aria-label="Listing photos">{photos.map((photo, index) => <button key={photo.id} type="button" onClick={() => setSelected(index)} aria-label={`Show photo ${index + 1}`} aria-pressed={selected === index} className={`overflow-hidden rounded-xl border-2 ${selected === index ? "border-[#064829]" : "border-transparent"}`}><Image unoptimized src={photo.url} alt="" width={96} height={72} className="h-[72px] w-24 object-cover" /></button>)}</div>}
  </div>;
}
