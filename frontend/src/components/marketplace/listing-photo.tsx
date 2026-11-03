"use client";

import { useEffect, useState } from "react";
import Image from "next/image";
import { legacyPhotos } from "@/lib/marketplace/legacy-photos";
import { MaterialPlaceholder } from "./material-placeholder";
import { MaterialVisual } from "./material-visual";
import { buyerListings } from "@/lib/data/buyer-fixtures";

const presentationIds = new Set(buyerListings.map((listing) => listing.id));
import { getVendorDemoPhoto } from "@/lib/data/vendor-listing-photos";

type ListingPhotoProps = {
  listingId: string;
  category: string;
  title: string;
  className?: string;
  compact?: boolean;
  preferLegacy?: boolean;
};

export function ListingPhoto({
  listingId,
  category,
  title,
  className = "",
  compact = false,
  preferLegacy = false,
}: ListingPhotoProps) {
  const [uploaded, setUploaded] = useState<{
    listingId: string;
    url: string | null;
  } | null>(null);
  const photoUrl = uploaded?.listingId === listingId ? uploaded.url : null;

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
        setUploaded({ listingId, url: objectUrl });
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
        <>
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img
            src={photoUrl}
            alt={`${title} — uploaded photo`}
            onError={() => setUploaded({ listingId, url: null })}
            className="absolute inset-0 h-full w-full object-cover"
          />
          <span
            className={`absolute bottom-1 left-1 max-w-[calc(100%-0.5rem)] rounded-full bg-white/95 px-2 py-1 font-semibold text-[#14211a] ${compact ? "text-[8px]" : "text-[10px]"}`}
          >
            Uploaded photo
          </span>
        </>
      ) : preferLegacy && legacyPhotos[listingId] ? (
        <>
          <Image
            src={legacyPhotos[listingId]}
            alt={`${title} — illustrative presentation image, not seller inventory`}
            fill
            sizes="(max-width: 639px) 100vw, (max-width: 1279px) 50vw, 400px"
            className="object-cover"
          />
          <span className="absolute inset-x-0 top-0 bg-[#102a1c]/95 px-2 py-1 text-center text-xs font-semibold text-white">
            Illustrative image · Not seller inventory
          </span>
        </>
      ) : (
        <div className="absolute inset-0">
          {presentationIds.has(listingId) ? (
            <MaterialVisual
              category={category}
              title={title}
              compact={compact}
              inventory
            />
          ) : (
            <MaterialPlaceholder
              category={category}
              title={title}
              compact={compact}
            />
          )}
        </div>
      )}
    </div>
  );
}
