import { describe, expect, it, vi, beforeEach } from 'vitest';

describe('api.clickSuggestion output_format', () => {
  beforeEach(() => {
    localStorage.clear();
  });

  it('sends structured output_format in the response payload', async () => {
    const { api } = await import('@/lib/api');
    const post = vi.fn().mockResolvedValue({ data: {} });
    (api as any).client.post = post;

    await api.clickSuggestion('s1', 'confirm_start', 'confirm text', undefined, 'pptx');

    expect(post).toHaveBeenCalledTimes(1);
    const formData = post.mock.calls[0][1] as FormData;
    const payload = JSON.parse(String(formData.get('response')));
    expect(payload).toMatchObject({
      suggestion_id: 'confirm_start',
      text: 'confirm text',
      output_format: 'pptx',
    });
  });

  it('omits output_format when not provided', async () => {
    const { api } = await import('@/lib/api');
    const post = vi.fn().mockResolvedValue({ data: {} });
    (api as any).client.post = post;

    await api.clickSuggestion('s1', 'confirm_start', 'confirm text');

    const formData = post.mock.calls[0][1] as FormData;
    const payload = JSON.parse(String(formData.get('response')));
    expect(payload.output_format).toBeUndefined();
  });
});
