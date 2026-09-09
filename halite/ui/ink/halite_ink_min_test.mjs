import React, {useState, useEffect} from 'react'
import {render, Text, Box} from 'ink'
const rows = Array.from({length: 12}, (_,i)=>`row${i}`)
function Show(){
  const [n,setN]=useState(0)
  useEffect(()=>{const id=setInterval(()=>setN(x=>x+1),400);return()=>clearInterval(id)},[])
  return React.createElement(Box,{flexDirection:'column'},
    React.createElement(Text,{color:'yellow'},`AA banner ${n}`),
    rows.map(r=>React.createElement(Text,{key:r},r)),
    React.createElement(Text,null,`status ${n}`))
}
render(React.createElement(Show))
