import { describe, expect, it } from 'vitest';

import { PAGE_SIZE, pageOf } from '../paging';

describe('pageOf', () => {
  it('asks for 20 rows at a time', () => {
    expect(PAGE_SIZE).toBe(20);
  });

  it('puts the first offset on page 1 and counts a part page as a page', () => {
    expect(pageOf(0, 45)).toEqual({ page: 1, pages: 3 });
  });

  it('finds the last page from its offset', () => {
    expect(pageOf(40, 45)).toEqual({ page: 3, pages: 3 });
  });

  it('fits exactly 20 on one page', () => {
    expect(pageOf(0, 20).pages).toBe(1);
    expect(pageOf(0, 21).pages).toBe(2);
  });

  it('has no pages for an empty list', () => {
    expect(pageOf(0, 0)).toEqual({ page: 1, pages: 0 });
  });
});
