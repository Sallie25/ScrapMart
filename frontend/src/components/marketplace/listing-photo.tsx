
"use client";

import { useEffect, useState } from "react";
import { getVendorDemoPhoto } from "@/lib/data/vendor-listing-photos";

type ListingPhotoProps = {
  listingId: string;
  category: string;
  title: string;
  className?: string;
};

function getCategoryEmoji(category: string) {
  switch (category) {
    case "Metals":
      return "🔩";
    case "Plastics":
      return "♻️";
    case "Paper":
      return "📦";
    default:
      return "⚙️";
  }
}

export function ListingPhoto({
  listingId,
  category,
  title,
  className = "",
}: ListingPhotoProps) {
  const [photoUrl, setPhotoUrl] = useState<string | null>(null);

  useEffect(() => {
    let active = true;
    let objectUrl: string | null = null;

    async function loadPhoto() {
      try {
        const photo = await getVendorDemoPhoto(listingId);

        if (!active || !photo) {
          return;
        }

        objectUrl = URL.createObjectURL(photo);
        setPhotoUrl(objectUrl);
      } catch {
        // Photos may be unavailable for older or sample listings.
      }
    }

    void loadPhoto();

    return () => {
      active = false;

      if (objectUrl) {
        URL.revokeObjectURL(objectUrl);
      }
    };
  }, [listingId]);

  return (
    <div
      className={`relative flex items-center justify-center overflow-hidden ${className}`}
    >
      {photoUrl ? (
        // eslint-disable-next-line @next/next/no-img-element
        <img
          src={photoUrl}
          alt={title}
          className="absolute inset-0 h-full w-full object-cover"
        />
      ) : (
        <div className="text-center" aria-label={`${category} placeholder`}>
          <div className="text-4xl" aria-hidden="true">
            {getCategoryEmoji(category)}
          </div>
          <p className="mt-2 text-xs text-muted">{category}</p>
        </div>
      )}
    </div>
  );
}
