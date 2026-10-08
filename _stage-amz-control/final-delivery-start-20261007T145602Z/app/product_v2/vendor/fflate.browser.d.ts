/**
 * Vendored fflate 0.8.3 browser build — accurate boundary for the two
 * synchronous ZIP functions actually used by storage/zip.js.
 * Do not edit the vendored JS; extend this file only if new fflate
 * entry points become used, keeping byte/options/result contracts exact.
 */

/**
 * Per-file ZIP entry options actually exercised (store level 0 + mtime).
 */
export interface FflateZipFileOptions {
  level?: number;
  mtime?: Date | number | string;
}

/**
 * Directory structure accepted by zipSync: path to raw bytes or to a
 * [bytes, per-file-options] tuple (the tuple form is what storage/zip.js uses).
 */
export type FflateZipInput = Record<string, Uint8Array | [Uint8Array, FflateZipFileOptions]>;

/**
 * Top-level options accepted by zipSync (storage/zip.js passes { level: 0 }).
 */
export interface FflateZipOptions {
  level?: number;
  mtime?: Date | number | string;
}

/**
 * Extraction filter entry passed to unzipSync when opts.filter is used.
 */
export interface FflateUnzipEntry {
  name: string;
  size: number;
  originalSize: number;
  compression: number;
}

/**
 * Extraction options accepted by unzipSync (storage/zip.js passes none).
 */
export interface FflateUnzipOptions {
  filter?: (entry: FflateUnzipEntry) => boolean;
}

/**
 * Synchronously create a ZIP archive from a directory structure.
 */
export function zipSync(data: FflateZipInput, opts?: FflateZipOptions): Uint8Array;

/**
 * Synchronously decompress a ZIP archive into path-keyed raw bytes.
 */
export function unzipSync(data: Uint8Array, opts?: FflateUnzipOptions): Record<string, Uint8Array>;
