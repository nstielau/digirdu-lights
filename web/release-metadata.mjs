const repo='nstielau/digirdu-lights';
export function githubReleaseUrl(version){
  return `https://github.com/${repo}/releases/tag/firmware-v${encodeURIComponent(version)}`;
}

export async function fetchReleaseMetadata(fetcher=fetch){
  const response=await fetcher(`https://api.github.com/repos/${repo}/releases?per_page=100`,
    {headers:{Accept:'application/vnd.github+json'}});
  if(!response.ok)throw new Error('github_releases_unavailable');
  const releases=await response.json();
  if(!Array.isArray(releases))throw new Error('github_releases_invalid');
  const metadata=new Map();
  for(const release of releases){
    const match=/^firmware-v(\d+\.\d+\.\d+)$/.exec(release.tag_name||'');
    if(!match||metadata.has(match[1]))continue;
    metadata.set(match[1],{publishedAt:release.published_at||null,
      notes:typeof release.body==='string'?release.body:'',url:githubReleaseUrl(match[1])});
  }
  return metadata;
}
