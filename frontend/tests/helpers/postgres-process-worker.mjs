// IPC only: synthetic identifiers/keys never go to stdout or application logs.
import { guard, pool, identity, session, CredentialVault } from './postgres-fixture.mjs';
await guard();
process.once('message', async message => {
  const db = pool();
  let store;
  try {
    await identity(db, 'scrapmart_bff_runtime');
    store = session(new CredentialVault('v1', { v1: Buffer.from(message.key, 'base64') }));
    if (message.mode === 'claim-and-crash') {
      await store.refresh(message.id, async () => {
        setInterval(() => {}, 1000); // Stay alive until the parent deliberately SIGKILLs this worker.
        process.send({ claimed: true });
        await new Promise(() => {});
      });
    } else {
      const available = Boolean(await store.lookup(message.id));
      const usable = await store.withAccess(message.id, async token => token === message.access);
      process.send({ available, usable });
    }
  } catch { process.send({ failed: true }); }
  finally { if (store) await store.close(); await db.end(); process.disconnect(); }
});
