





## make new posts
> hugo new content/post/2019-12-26-childcare.md

## To run and deploy from local:
commands for hugo

To run locally
> hugo server -D


To deploy to Firebase
> hugo && firebase deploy


## To set up CI on Travis
following this guide: https://medium.com/@bartwijnants/continuous-deployment-to-firebase-hosting-using-travis-ci-e7d9c798ead4

First get a firebase cli token
``` 
firebase login:ci
```
Then encrypt this token into travis 
(as the poster of the blog, I had trouble installing Ruby locally for some reason so I used docker for it)
``` 
docker run -it --rm ruby:latest bash
gem install travis
travis encrypt "1/firebase_CI_token" -r githubusername/reponame
```

then add that encrypted token to `.travis.yml`
(it's ok to put it in github since it's encrypted)

```
language: node_js
node_js:
  - "node"
install:
  - curl -LO https://github.com/gohugoio/hugo/releases/download/v0.55.4/hugo_0.55.4_Linux-64bit.deb
  - sudo dpkg -i hugo_0.55.4_Linux-64bit.deb
script:
  - hugo
deploy:
  provider: firebase
  token:
    secure: "encrypted_firebase_CI_token"
```
