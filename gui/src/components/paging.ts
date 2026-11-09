/** How many rows the Games and Players lists ask the API for at once */
export const PAGE_SIZE = 20;

/** Which page an offset falls on, counting from 1, and how many pages there are. */
export function pageOf(offset: number, total: number): { page: number; pages: number } {
  return { page: Math.floor(offset / PAGE_SIZE) + 1, pages: Math.ceil(total / PAGE_SIZE) };
}
