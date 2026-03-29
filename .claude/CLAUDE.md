  ## Git Credentials                                                                                                                                              
  Git credentials for GitHub (highfrog account) are stored via `git credential.helper store` at `~/.git-credentials`.                                             
  To authenticate `gh` CLI from stored credentials:                                                                                                               
  token=$(cat ~/.git-credentials | grep github.com | head -1 | sed 's|https://highfrog:\(.*\)@github.com|\1|') && echo "$token" | gh auth login --with-token      
  Org for public repos: `reedylab` 