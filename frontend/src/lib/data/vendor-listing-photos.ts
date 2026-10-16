
const DATABASE_NAME = "scrapmart-vendor-demo-photos";
const STORE_NAME = "photos";

type StoredPhoto = {
  listingId: string;
  blob: Blob;
  updatedAt: string;
};

function openPhotoDatabase(): Promise<IDBDatabase> {
  return new Promise((resolve, reject) => {
    if (typeof window === "undefined" || !("indexedDB" in window)) {
      reject(new Error("Browser photo storage is unavailable."));
      return;
    }

    const request = window.indexedDB.open(DATABASE_NAME, 1);

    request.onupgradeneeded = () => {
      const database = request.result;

      if (!database.objectStoreNames.contains(STORE_NAME)) {
        database.createObjectStore(STORE_NAME, {
          keyPath: "listingId",
        });
      }
    };

    request.onsuccess = () => resolve(request.result);
    request.onerror = () =>
      reject(request.error ?? new Error("Could not open photo storage."));
  });
}

export async function saveVendorDemoPhoto(
  listingId: string,
  file: Blob,
): Promise<void> {
  const database = await openPhotoDatabase();

  try {
    await new Promise<void>((resolve, reject) => {
      const transaction = database.transaction(STORE_NAME, "readwrite");

      transaction.objectStore(STORE_NAME).put({
        listingId,
        blob: file,
        updatedAt: new Date().toISOString(),
      } satisfies StoredPhoto);

      transaction.oncomplete = () => resolve();
      transaction.onerror = () =>
        reject(transaction.error ?? new Error("Could not save photo."));
      transaction.onabort = () =>
        reject(transaction.error ?? new Error("Photo saving was cancelled."));
    });
  } finally {
    database.close();
  }
}

export async function getVendorDemoPhoto(
  listingId: string,
): Promise<Blob | null> {
  const database = await openPhotoDatabase();

  try {
    return await new Promise<Blob | null>((resolve, reject) => {
      const transaction = database.transaction(STORE_NAME, "readonly");
      const request = transaction.objectStore(STORE_NAME).get(listingId);

      request.onsuccess = () => {
        const result = request.result as StoredPhoto | undefined;
        resolve(result?.blob ?? null);
      };

      request.onerror = () =>
        reject(request.error ?? new Error("Could not load photo."));
    });
  } finally {
    database.close();
  }
}

export async function deleteVendorDemoPhoto(
  listingId: string,
): Promise<void> {
  const database = await openPhotoDatabase();

  try {
    await new Promise<void>((resolve, reject) => {
      const transaction = database.transaction(STORE_NAME, "readwrite");
      transaction.objectStore(STORE_NAME).delete(listingId);

      transaction.oncomplete = () => resolve();
      transaction.onerror = () =>
        reject(transaction.error ?? new Error("Could not delete photo."));
      transaction.onabort = () =>
        reject(transaction.error ?? new Error("Photo deletion was cancelled."));
    });
  } finally {
    database.close();
  }
}
